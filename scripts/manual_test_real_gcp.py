#!/usr/bin/env python3
"""Like scripts/manual_test.py, but against your real Firestore + GCS
instead of in-memory fakes — real signed GCS URLs, a real public HF Hub
dataset, real worker-side download into the LRU cache. Only the reCAPTCHA
verifier and HF OAuth client are faked, since neither has a browser
available to produce a real token/OAuth code.

This writes real data into your real Firestore database and GCS bucket
(a demo user, at least one job document, an uploaded/downloaded object).
Nothing here deletes it automatically — clean up manually afterward if
you care to (see the printed reminder on exit).

Prerequisites: GOOGLE_APPLICATION_CREDENTIALS set, the service account
granted `roles/datastore.user` + `roles/storage.objectAdmin` (see
deploy/README.md), the Firestore database created, and its two composite
indexes (user_id+created_at, status+created_at on the `jobs` collection)
already built.

Usage:
    uv run python scripts/manual_test_real_gcp.py \\
        --project-id YOUR_PROJECT --database-id YOUR_DATABASE --bucket YOUR_BUCKET
"""

from __future__ import annotations

import argparse
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

from backend.adapters.firestore.job_repository import FirestoreJobRepository  # noqa: E402
from backend.adapters.firestore.user_repository import FirestoreUserRepository  # noqa: E402
from backend.adapters.gcs.object_storage import GCSObjectStorage  # noqa: E402
from backend.adapters.hf.hf_hub_client import RealHFHubClient  # noqa: E402
from backend.adapters.memory import InMemoryCaptchaVerifier, InMemoryHFOAuthClient  # noqa: E402
from backend.config import Settings  # noqa: E402
from backend.deps import build_dependencies  # noqa: E402
from backend.main import build_app  # noqa: E402
from worker import main as worker_main  # noqa: E402
from worker.config import WorkerSettings  # noqa: E402
from worker.deps import build_worker_dependencies  # noqa: E402
from worker.docker_runner import DockerRunner  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")
logger = logging.getLogger("manual_test_real_gcp")

ACT_IMAGE = "lerobot-train-act:latest"
SMOLVLA_IMAGE = "lerobot-train-smolvla:latest"
DEMO_EMAIL = "manual-test-real-gcp@example.com"


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


def print_walkthrough(base_url: str, repo_id: str, policy: str, training_steps: int, project_id: str, bucket: str) -> None:
    print(
        f"""
{'=' * 70}
Backend running at {base_url}  (interactive docs: {base_url}/docs)
Worker polling with real Docker containers, against:
  GCP project:    {project_id}
  GCS bucket:     {bucket}
Real public HF Hub dataset: {repo_id}
(reCAPTCHA + HF OAuth are FAKED for this test — see module docstring.)

--- Example curl walkthrough ---

curl -s -X POST {base_url}/auth/register -H 'Content-Type: application/json' \\
  -d '{{"email":"{DEMO_EMAIL}","password":"password123","captcha_token":"x"}}'

TOKEN=$(curl -s -X POST {base_url}/auth/login -H 'Content-Type: application/json' \\
  -d '{{"email":"{DEMO_EMAIL}","password":"password123"}}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl -s -X POST {base_url}/uploads/hf-dataset -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \\
  -d '{{"repo_id":"{repo_id}","policy":"{policy}","training_steps":{training_steps}}}'

curl -s {base_url}/jobs -H "Authorization: Bearer $TOKEN"

# Once status is "completed":
JOB_ID=<id from above>
curl -s {base_url}/jobs/$JOB_ID/download-url -H "Authorization: Bearer $TOKEN"
# -> a REAL storage.googleapis.com signed URL this time; curl -o it directly.

--- Cleanup reminder (nothing here is auto-deleted) ---
- Firestore: delete the "users" doc for {DEMO_EMAIL} and any "jobs" docs it created
  (console, or gcloud firestore ... if you have the CLI installed).
- GCS: delete anything left under gs://{bucket}/checkpoints/ or gs://{bucket}/uploads/
  (the zip-upload path already self-deletes its source object; hf_hub jobs
  never write to GCS except the final checkpoint).
{'=' * 70}
Ctrl+C to stop.
"""
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--database-id", default="(default)")
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--workdir", default="/tmp/lerobot-manual-test-real-gcp")
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--hf-repo-id", default="lerobot/pusht", help="A real public LeRobot v3 dataset repo.")
    parser.add_argument("--policy", choices=["act", "smolvla"], default="act")
    parser.add_argument("--training-steps", type=int, default=20)
    args = parser.parse_args()

    base_url = f"http://{args.host}:{args.port}"
    workdir = Path(args.workdir)
    workdir.mkdir(parents=True, exist_ok=True)

    build_images_if_needed(args.skip_build)

    from google.cloud import firestore, storage

    firestore_client = firestore.Client(project=args.project_id, database=args.database_id)
    gcs_client = storage.Client(project=args.project_id)

    user_repo = FirestoreUserRepository(firestore_client)
    job_repo = FirestoreJobRepository(firestore_client)
    object_storage = GCSObjectStorage(gcs_client, args.bucket)
    hf_hub = RealHFHubClient()
    captcha = InMemoryCaptchaVerifier()
    hf_oauth = InMemoryHFOAuthClient()

    backend_settings = Settings(
        use_fake_adapters=False,
        gcp_project_id=args.project_id,
        firestore_database_id=args.database_id,
        gcs_bucket=args.bucket,
        jwt_secret="manual-test-real-gcp-jwt-secret-change-me",
        scheduler_shared_secret="manual-test-real-gcp-scheduler-secret",
    )
    backend_deps = build_dependencies(
        backend_settings,
        user_repository=user_repo,
        job_repository=job_repo,
        storage=object_storage,
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
        use_gpu=False,
        workdir=str(workdir / "jobs"),
        hf_cache_dir=str(workdir / "hf-cache"),
        poll_interval_seconds=args.poll_interval,
        act_image=ACT_IMAGE,
        smolvla_image=SMOLVLA_IMAGE,
        gcs_bucket=args.bucket,
        gcp_project_id=args.project_id,
        firestore_database_id=args.database_id,
    )
    worker_deps = build_worker_dependencies(
        worker_settings,
        job_repository=job_repo,
        user_repository=user_repo,
        docker_client=DockerRunner(),
        object_storage=object_storage,
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

    print_walkthrough(base_url, args.hf_repo_id, args.policy, args.training_steps, args.project_id, args.bucket)

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
