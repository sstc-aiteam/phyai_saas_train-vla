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
Dockerfile              # packages backend.main:app for Cloud Run (spec section 2)
.dockerignore
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
    api/               # thin HTTP routers (+ dev_storage.py, dev-mode only)
    services/          # use-case layer: orchestrates ports + domain rules
    security/          # password hashing, JWT
    deps.py             # chooses real-vs-fake adapters per Settings.use_fake_adapters
    adapters/          # real Firestore / GCS / HF Hub / HF OAuth / reCAPTCHA clients
                        # + in-memory adapters used for local dev (no GCP creds needed)
  worker/              # GPU host process (systemd, Restart=always)
    deps.py             # chooses real-vs-fake adapters per WorkerSettings.use_fake_adapters
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
  firestore.indexes.json  # composite indexes FirestoreJobRepository's queries need
  worker.env.example      # env vars the systemd unit expects
scripts/
  manual_test.py            # runs backend + worker in one process against shared in-memory
                             # state + real Docker, for manual curl-based end-to-end testing
  manual_test_real_gcp.py   # same, but against a real Firestore + GCS project
  make_demo_dataset_zip.py  # writes a validly-shaped demo dataset zip for the upload path
tests/
  common/              # pure unit tests for the domain rules, no mocks
  backend/             # service-layer + API-layer tests, using in-memory fakes
  worker/              # worker orchestration tests, using in-memory fakes + tmp_path
  docker/              # tests for the training-container entrypoint contract
```

## Running

```bash
uv sync
uv run pytest              # 220 tests, all using fakes/tmp_path — no GCP/Docker/GPU needed
uv run uvicorn backend.main:app --reload   # local dev server, in-memory adapters by default
```

By default `Settings.use_fake_adapters=True`, so the API runs against
in-memory storage (`backend/adapters/memory.py`) — good for local dev and
for the "does the app assemble" smoke test, but data doesn't persist across
restarts and HF OAuth login always fails (no real IdP to talk to). Set
`LEROBOT_USE_FAKE_ADAPTERS=false` plus the GCP/HF/reCAPTCHA env vars (see
`backend/config.py`) to run against real infrastructure. `WorkerSettings`
has the same `use_fake_adapters` toggle (default `False` — a real worker
touching real Docker/GPU should never silently fall back to fake mode).

### Manual end-to-end testing (no GCP required)

Running the backend and worker as two separate processes only actually
connects them once both point at a real Firestore project + GCS bucket —
their fake/in-memory modes are each self-contained and don't talk to each
other. `scripts/manual_test.py` sidesteps this for manual testing by
running both as threads *in one process*, sharing the same in-memory
job/user/dataset store, with a real Docker daemon underneath:

```bash
uv run python scripts/manual_test.py          # builds the two demo images, then serves on :8765
```

It prints a `curl` walkthrough covering both dataset paths (a seeded fake
HF Hub repo, and a real zip upload via `scripts/make_demo_dataset_zip.py`
+ a local dev-storage stand-in for GCS at `/dev-storage/...`). Verified
manually: both paths go all the way through `queued → initializing →
training → completed` and produce a real, downloadable checkpoint zip.

### Manual end-to-end testing against real GCP

`scripts/manual_test_real_gcp.py` is the same idea, wired to a real
Firestore database + GCS bucket instead (real signed URLs, a real public
HF Hub dataset) — only reCAPTCHA/HF OAuth stay faked, since neither has a
browser available to produce a real token/code here:

```bash
uv run python scripts/manual_test_real_gcp.py \
  --project-id YOUR_PROJECT --database-id YOUR_DATABASE --bucket YOUR_BUCKET
```

See [`deploy/README.md`](deploy/README.md) for the one-time Firestore
database + composite-index + IAM setup this needs first. It writes real
data and does not clean up after itself — see the script's own printed
reminder.

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
  hand instead; keep them small if you touch them. (`firestore/*` and
  `gcs/*` were, however, exercised against a real GCP project manually —
  see below; `hf/hf_hub_client.py` and `worker/docker_runner.py` too.
  `hf/hf_oauth_client.py` and `recaptcha/verifier.py` are the two pieces
  genuinely never run against anything real, real or otherwise — no
  browser/OAuth app available to produce a token/code.)
- The two `docker/*/Dockerfile` images were built and run manually during
  development (`docker build` + `docker run`) to confirm the
  `train_entrypoint.py` contract actually produces `progress.json` and a
  checkpoint directory in the shape the worker expects.
- The full `JobPoller` -> `DatasetFetcher` -> container -> `JobCompletionMonitor`
  -> checkpoint upload pipeline was run end-to-end against a real `docker`
  daemon for both source types (`hf_hub` and `zip_upload`), using
  `DockerRunner` for real and fakes only for Firestore/HF-Hub-API/GCS —
  first as a throwaway script (which caught three real bugs unit tests
  alone couldn't have: the `ContainerSpec` command duplicated the image's
  own `ENTRYPOINT`, its volume mount shadowed `/workspace/train_entrypoint.py`
  in the image, and containers ran as root, leaving files the non-root
  worker process couldn't later package or delete — all fixed, see git
  history), then again through the full HTTP API via `scripts/manual_test.py`
  and `curl` (register → login → submit job → poll → download), for both
  dataset paths. This sandbox has no GPU driver, so both runs used
  `use_gpu=False` (now a proper `JobPoller`/`WorkerSettings` option, not a
  monkeypatch) — production still defaults to `use_gpu=True`.
- The same pipeline was then run a third time against a **real GCP
  project** (`scripts/manual_test_real_gcp.py`): real Firestore (a named,
  non-default database — required adding `Settings.firestore_database_id`
  and threading it through `firestore.Client(database=...)`, which wasn't
  needed before), a real GCS bucket with real V4-signed upload/download
  URLs, and a real public HF Hub dataset (`lerobot/pusht`, confirmed to
  actually pass `check_lerobot_structure`/`check_policy_compatibility`
  before relying on it). Caught a real gap: two of
  `FirestoreJobRepository`'s queries need a Firestore composite index that
  doesn't exist until you create it once — see `deploy/README.md` and
  `deploy/firestore.indexes.json`. Register → login → submit → real
  dataset download into the LRU cache → real container → real checkpoint
  uploaded to and downloaded back from `storage.googleapis.com` all
  worked; test data was cleaned up manually afterward (nothing here does
  that automatically — see the script's own printed reminder).
- The root `Dockerfile` (packages the backend for Cloud Run) was built and
  run locally against both fake and real adapters — the latter with the
  real service account key mounted in, confirming `/internal/check-timeouts`
  reaches real Firestore (through the composite indexes) from inside the
  container exactly as it would on Cloud Run. Not actually deployed to
  Cloud Run itself: that needs a `gcloud` session with deploy-time rights
  the app's own least-privilege runtime service account intentionally
  doesn't have — see `deploy/README.md`.

## Scope and known gaps

Deliberately left out of this pass (see the spec for what they should do):

- **React frontend** — not built.
- **Real ACT/SmolVLA training** — `docker/*/train_entrypoint.py` is a
  contract stub: it checks `--input-dir` is populated and writes
  `progress.json`/a checkpoint directory on schedule, but doesn't actually
  load the dataset or train a model. Swap in real `lerobot` training code
  without changing the CLI contract the worker depends on.
- HF OAuth login and reCAPTCHA verification are real code, verified only
  by review — neither can be exercised without a browser (no frontend
  exists to produce a real OAuth code or reCAPTCHA token).
- **Backend deployed to Cloud Run**: live at
  `https://lerobot-backend-526282644766.us-central1.run.app` (project
  `sstc-aiteam`), talking to the real Firestore/GCS from earlier. Verified
  `/docs`, `/internal/check-timeouts` (real Firestore), and that the old
  default `LEROBOT_JWT_SECRET`/`LEROBOT_SCHEDULER_SHARED_SECRET` are gone
  (real random values now, generated at deploy time). **TODO**: those two
  are still plain Cloud Run env vars, not Secret Manager — see
  `deploy/README.md`'s "Deployed status"/"TODO" for the exact follow-up.
- Cloud Scheduler (spec section 4) isn't provisioned yet — see
  [`deploy/README.md`](deploy/README.md) for the one-line `gcloud` command
  to point it at `/internal/check-timeouts` (there's now a real URL to
  point it at).
- Dataset fetching (`dataset_fetcher.py`) runs synchronously inside
  `JobPoller.tick()`, blocking the poll loop for as long as the download
  takes. On a well-connected host this should comfortably fit inside the
  5-minute `initializing` timeout for the spec's 2GB dataset cap, but
  nothing currently refreshes the heartbeat *during* a long download —
  worth watching if real-world fetches turn out slower than expected.
