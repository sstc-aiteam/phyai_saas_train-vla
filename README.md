# LeRobot Training Service

Backend API + GPU worker for the service described in
[`lerobot-training-service-spec.md`](lerobot-training-service-spec.md).

This implementation covers the **backend API (FastAPI) and the GPU worker's
core orchestration logic**. The React frontend and the real ACT/SmolVLA
`lerobot` training code are out of scope for this pass — see
[Scope and known gaps](#scope-and-known-gaps).

## Architecture

Hexagonal / ports-and-adapters: all business rules live in pure,
dependency-free modules under `src/common/domain/`; everything that talks
to an external system (Firestore, GCS, Docker, HF Hub, HF OAuth, reCAPTCHA)
sits behind an interface in `src/common/ports/`, with a real adapter and a
test fake for each.

```
src/
  common/
    models.py         # User, Job, JobStatus, PolicyType, SourceType, Progress
    ports/             # abstract interfaces for every external dependency
    domain/            # pure business rules — the part that's most heavily tested
      job_state_machine.py   # queued -> initializing -> training -> completed/failed/cancelled
      quota.py                # concurrent-job limit + daily quota
      heartbeat.py            # initializing (5min) / training (2min) timeout rules
      dataset_validation.py   # LeRobot v3 structure + decompression-bomb checks
      policy_shapes.py        # observation/action shape vs selected policy
      limits.py                # training-step cap
  backend/             # FastAPI app
    api/               # thin HTTP routers
    services/          # use-case layer: orchestrates ports + domain rules
    security/          # password hashing, JWT
    adapters/          # real Firestore / GCS / HF Hub / HF OAuth / reCAPTCHA clients
                        # + in-memory adapters used for local dev (no GCP creds needed)
  worker/              # GPU host process (systemd, Restart=always)
    job_poller.py      # picks the next queued job, fetches its dataset, starts its container, tracks daily quota
    dataset_fetcher.py  # HF Hub download into the LRU cache, or GCS zip extraction, before container start
    job_completion.py  # monitors the active job: progress -> training, exit -> completed/failed
    progress_reader.py    # reads progress.json off the shared volume
    checkpoint_packager.py  # zips a finished checkpoint dir for upload
    cancel_watcher.py  # handles cancel_requested for queued/initializing/training jobs
    orphan_reconciler.py  # on restart: resume tracked containers, kill orphans
    heartbeat_updater.py  # bumps Firestore heartbeat per spec's per-status rules
    disk_manager.py    # HF dataset cache LRU eviction, stale .tmp cleanup
    lock.py             # flock-based single-flight lock (one training container at a time)
    docker_runner.py    # real docker-py adapter
docker/
  act/, smolvla/       # one Dockerfile + train_entrypoint.py per policy (see below)
deploy/
  lerobot-worker.service  # systemd unit for worker/main.py (Restart=always)
  gcs-lifecycle.json      # bucket lifecycle rules (orphaned uploads, checkpoint expiry)
  worker.env.example      # env vars the systemd unit expects
tests/
  common/              # pure unit tests for the domain rules, no mocks
  backend/             # service-layer + API-layer tests, using in-memory fakes
  worker/              # worker orchestration tests, using in-memory fakes + tmp_path
  docker/              # tests for the training-container entrypoint contract
```

## Running

```bash
uv sync
uv run pytest              # 203 tests, all using fakes/tmp_path — no GCP/Docker/GPU needed
uv run uvicorn backend.main:app --reload   # local dev server, in-memory adapters by default
```

By default `Settings.use_fake_adapters=True`, so the API runs against
in-memory storage (`backend/adapters/memory.py`) — good for local dev and
for the "does the app assemble" smoke test, but data doesn't persist across
restarts and HF OAuth login always fails (no real IdP to talk to). Set
`LEROBOT_USE_FAKE_ADAPTERS=false` plus the GCP/HF/reCAPTCHA env vars (see
`backend/config.py`) to run against real infrastructure.

## What's genuinely tested vs. what's a thin wire-up

- **Fully unit-tested**: everything under `common/domain/`, all backend
  services (`auth_service`, `job_service`, `upload_service`,
  `timeout_service`), the API layer (via `TestClient` + dependency
  injection), and all worker orchestration modules (`job_poller`,
  `dataset_fetcher`, `job_completion`, `progress_reader`,
  `checkpoint_packager`, `cancel_watcher`, `orphan_reconciler`,
  `heartbeat_updater`, `disk_manager`, `lock`).
- **Not unit-tested here** (thin translation layers with no business logic
  of their own — would need a Firestore/GCS emulator or a real Docker
  daemon to test meaningfully): `backend/adapters/firestore/*`,
  `backend/adapters/gcs/*`, `backend/adapters/hf/*`,
  `backend/adapters/recaptcha/*`, `worker/docker_runner.py`. Reviewed by
  hand instead; keep them small if you touch them.
- The two `docker/*/Dockerfile` images were built and run manually during
  development (`docker build` + `docker run`) to confirm the
  `train_entrypoint.py` contract actually produces `progress.json` and a
  checkpoint directory in the shape the worker expects.
- The full `JobPoller` -> `DatasetFetcher` -> container -> `JobCompletionMonitor`
  -> checkpoint upload pipeline was also run end-to-end against a real
  `docker` daemon for both source types (`hf_hub` and `zip_upload`), using
  `DockerRunner` for real and fakes only for Firestore/HF-Hub-API/GCS. That
  first run (before dataset fetching existed) caught three real bugs unit
  tests alone couldn't have: the `ContainerSpec` command duplicated the
  image's own `ENTRYPOINT`, its volume mount shadowed
  `/workspace/train_entrypoint.py` in the image, and containers ran as
  root, leaving files the (non-root) worker process couldn't later package
  or delete. All three are fixed in `job_poller.py`/`docker_runner.py` —
  see git history for details. (This sandbox has no GPU driver, so that
  check ran with `use_gpu=False` monkeypatched in for the test only —
  production `job_poller.py` still hardcodes `use_gpu=True`.)

## Scope and known gaps

Deliberately left out of this pass (see the spec for what they should do):

- **React frontend** — not built.
- **Real ACT/SmolVLA training** — `docker/*/train_entrypoint.py` is a
  contract stub: it checks `--input-dir` is populated and writes
  `progress.json`/a checkpoint directory on schedule, but doesn't actually
  load the dataset or train a model. Swap in real `lerobot` training code
  without changing the CLI contract the worker depends on.
- Firestore/GCS/HF/reCAPTCHA adapters are real but unverified against live
  services in this environment (no credentials available here).
- Cloud Scheduler (spec section 4) isn't provisioned — see
  [`deploy/README.md`](deploy/README.md) for the one-line `gcloud` command
  to point it at `/internal/check-timeouts`.
- Dataset fetching (`dataset_fetcher.py`) runs synchronously inside
  `JobPoller.tick()`, blocking the poll loop for as long as the download
  takes. On a well-connected host this should comfortably fit inside the
  5-minute `initializing` timeout for the spec's 2GB dataset cap, but
  nothing currently refreshes the heartbeat *during* a long download —
  worth watching if real-world fetches turn out slower than expected.
