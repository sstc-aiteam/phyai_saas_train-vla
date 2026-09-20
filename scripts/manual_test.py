#!/usr/bin/env python3
"""Runs the backend API and a worker loop in this one process, sharing the
same in-memory Firestore/GCS/HF-Hub stand-ins, so you can manually exercise
the whole queued -> initializing -> training -> completed pipeline over
HTTP (curl, httpie, a browser at /docs, ...) without any real GCP project,
Docker Hub credentials beyond a local `docker build`, or GPU.

This only works because both "processes" here are threads in the same
Python process sharing the same InMemory* adapter instances — a real
deployment always has the backend and worker as separate processes talking
through real Firestore/GCS, which is what makes this a *manual test
harness*, not a second way to run the service.

Usage:
    uv run python scripts/manual_test.py [--port 8765] [--skip-build]

Then, in another terminal, see the printed curl walkthrough, or open
http://127.0.0.1:8765/docs for interactive API docs. Ctrl+C to stop.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import uvicorn

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from backend.adapters.memory import (  # noqa: E402
    InMemoryCaptchaVerifier,
    InMemoryHFHubClient,
    InMemoryHFOAuthClient,
    InMemoryJobRepository,
    InMemoryObjectStorage,
    InMemoryUserRepository,
)
from backend.config import Settings  # noqa: E402
from backend.deps import build_dependencies  # noqa: E402
from backend.main import build_app  # noqa: E402
from worker import main as worker_main  # noqa: E402
from worker.config import WorkerSettings  # noqa: E402
from worker.deps import build_worker_dependencies  # noqa: E402
from worker.docker_runner import DockerRunner  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
logger = logging.getLogger("manual_test")

DEMO_REPO_ID = "demo/pick-place"
ACT_IMAGE = "lerobot-train-act:latest"
SMOLVLA_IMAGE = "lerobot-train-smolvla:latest"


def seed_demo_hf_repo(hf_hub: InMemoryHFHubClient) -> None:
    info_json = {
        "features": {
            "observation.state": {"shape": [14]},
            "action": {"shape": [7]},
            "observation.images.top": {"shape": [3, 224, 224]},
        }
    }
    hf_hub.add_repo(
        DEMO_REPO_ID,
        {
            "meta/info.json": json.dumps(info_json).encode("utf-8"),
            "data/chunk-000/episode_000000.parquet": b"placeholder-not-real-parquet-data",
        },
    )


def build_images_if_needed(skip: bool) -> None:
    if skip:
        return
    for image, context_dir in [(ACT_IMAGE, "act"), (SMOLVLA_IMAGE, "smolvla")]:
        logger.info("Building %s (docker build)...", image)
        subprocess.run(
            ["docker", "build", "-q", "-t", image, str(REPO_ROOT / "docker" / context_dir)],
            check=True,
        )


def wait_until_serving(base_url: str, timeout_seconds: float = 10.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            httpx.get(f"{base_url}/docs", timeout=1.0)
            return
        except httpx.HTTPError:
            time.sleep(0.2)
    raise RuntimeError(f"Backend did not start serving at {base_url} within {timeout_seconds}s")


def print_walkthrough(base_url: str, workdir: Path) -> None:
    print(
        f"""
{'=' * 70}
Backend running at {base_url}  (interactive docs: {base_url}/docs)
Worker polling every few seconds, using real Docker containers.
Job/checkpoint working directory: {workdir}

Seeded demo HF Hub repo: "{DEMO_REPO_ID}" (works for either policy).
For a zip-upload dataset instead, first run:
    uv run python scripts/make_demo_dataset_zip.py --policy act --out demo_dataset.zip

--- Example curl walkthrough (HF Hub dataset path) ---

# 1. Register + log in
curl -s -X POST {base_url}/auth/register -H 'Content-Type: application/json' \\
  -d '{{"email":"demo@example.com","password":"password123","captcha_token":"x"}}'

TOKEN=$(curl -s -X POST {base_url}/auth/login -H 'Content-Type: application/json' \\
  -d '{{"email":"demo@example.com","password":"password123"}}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# 2. Submit a training job against the seeded demo HF dataset
curl -s -X POST {base_url}/uploads/hf-dataset -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \\
  -d '{{"repo_id":"{DEMO_REPO_ID}","policy":"act","training_steps":20}}'

# 3. Poll job status (queued -> running -> completed)
curl -s {base_url}/jobs -H "Authorization: Bearer $TOKEN"

# 4. Once status is "completed", get + follow the download URL
JOB_ID=<id from step 2 or 3>
curl -s {base_url}/jobs/$JOB_ID/download-url -H "Authorization: Bearer $TOKEN"

--- Zip-upload path instead of step 2 ---

curl -s -X POST {base_url}/uploads/zip/target -H "Authorization: Bearer $TOKEN" \\
  | tee /tmp/upload_target.json
UPLOAD_URL=$(python3 -c "import json;print(json.load(open('/tmp/upload_target.json'))['upload_url'])")
UPLOAD_ID=$(python3 -c "import json;print(json.load(open('/tmp/upload_target.json'))['upload_id'])")
curl -s -X PUT "$UPLOAD_URL" --data-binary @demo_dataset.zip
curl -s -X POST {base_url}/uploads/zip/confirm -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \\
  -d "{{\\"upload_id\\":\\"$UPLOAD_ID\\",\\"policy\\":\\"act\\",\\"training_steps\\":20}}"
{'=' * 70}
Ctrl+C to stop.
"""
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--workdir", default=None, help="Defaults to a fresh dir under the system temp dir.")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--skip-build", action="store_true", help="Skip `docker build` for the demo images.")
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"
    workdir = Path(args.workdir) if args.workdir else Path("/tmp/lerobot-manual-test")
    workdir.mkdir(parents=True, exist_ok=True)

    build_images_if_needed(args.skip_build)

    # --- shared in-memory state between the "backend" and "worker" ---
    user_repo = InMemoryUserRepository()
    job_repo = InMemoryJobRepository()
    storage = InMemoryObjectStorage(base_url=base_url)
    hf_hub = InMemoryHFHubClient()
    seed_demo_hf_repo(hf_hub)
    captcha = InMemoryCaptchaVerifier()
    hf_oauth = InMemoryHFOAuthClient()

    backend_settings = Settings(
        use_fake_adapters=True,
        dev_storage_base_url=base_url,
        jwt_secret="manual-test-jwt-secret",
        scheduler_shared_secret="manual-test-scheduler-secret",
    )
    backend_deps = build_dependencies(
        backend_settings,
        user_repository=user_repo,
        job_repository=job_repo,
        storage=storage,
        hf_hub_client=hf_hub,
        captcha_verifier=captcha,
        hf_oauth_client=hf_oauth,
    )
    app = build_app(settings=backend_settings, deps=backend_deps)

    server = uvicorn.Server(uvicorn.Config(app, host=args.host, port=args.port, log_level="warning"))
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()
    wait_until_serving(base_url)
    logger.info("Backend is up at %s", base_url)

    worker_settings = WorkerSettings(
        use_gpu=False,  # manual testing rarely has a GPU on hand; production always sets this True
        workdir=str(workdir / "jobs"),
        hf_cache_dir=str(workdir / "hf-cache"),
        poll_interval_seconds=args.poll_interval,
        act_image=ACT_IMAGE,
        smolvla_image=SMOLVLA_IMAGE,
    )
    worker_deps = build_worker_dependencies(
        worker_settings,
        job_repository=job_repo,
        user_repository=user_repo,
        docker_client=DockerRunner(),
        object_storage=storage,
        hf_hub_client=hf_hub,
    )

    stop_event = threading.Event()

    def worker_loop() -> None:
        logger.info("Worker loop started (poll every %.1fs)", worker_settings.poll_interval_seconds)
        while not stop_event.is_set():
            worker_main.tick(worker_deps)
            stop_event.wait(worker_settings.poll_interval_seconds)

    worker_thread = threading.Thread(target=worker_loop, daemon=True)
    worker_thread.start()

    print_walkthrough(base_url, workdir)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        stop_event.set()
        server.should_exit = True
        worker_thread.join(timeout=5)
        server_thread.join(timeout=5)


if __name__ == "__main__":
    main()
