# LeRobot Training Service

Backend API + GPU worker for the service described in
[`lerobot-training-service-spec.md`](lerobot-training-service-spec.md).

This implementation covers the **backend API (FastAPI), the GPU worker's
core orchestration logic, and real ACT/SmolVLA training** (see
[Real ACT/SmolVLA training](#real-actsmolvla-training)). The React frontend
is out of scope for this pass — see
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
uv run pytest              # 207 tests, all using fakes/tmp_path — no GCP/Docker/GPU needed
                           # (+1 skipped: the docker/ entrypoint tests need
                           # the optional `lerobot` dependency, only present
                           # inside the training images, not this project's
                           # own venv)
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
- The two `docker/*/Dockerfile` images run real `lerobot` training (see
  "Real ACT/SmolVLA training" above), not the earlier stub, so
  `tests/docker/test_train_entrypoint_contract.py` now only unit-tests the
  torch/lerobot-free parts (CLI parsing, `--input-dir` validation,
  `progress.json`'s write shape) and skips entirely via
  `pytest.importorskip("lerobot")` when that optional dependency isn't
  installed (it never is in this project's own `pyproject.toml` — only the
  training images have it). The training loop and checkpoint writer
  themselves were instead built and run manually against the real RTX 4090
  host, confirming they produce `progress.json` and a checkpoint directory
  in the shape the worker expects, with real weights inside.
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

## Real ACT/SmolVLA training

`docker/act/train_entrypoint.py` and `docker/smolvla/train_entrypoint.py` run
real `lerobot` (0.6.1) training, not the earlier contract stub. Both load the
LeRobot v3 dataset the worker mounts at `--input-dir` via `LeRobotDataset`,
build the policy from its official defaults (only `--training-steps` is
spec-tunable), run a plain single-GPU training loop, and save a real
checkpoint (`policy.save_pretrained` + pre/postprocessor `save_pretrained`,
i.e. weights + `config.json` + normalization stats) to
`--output-dir/checkpoint` — the same directory `worker/checkpoint_packager.py`
already zips.

- **ACT** trains from scratch (ImageNet-pretrained ResNet-18 vision backbone,
  everything else random init), matching the spec's per-job/per-dataset
  training model.
- **SmolVLA** *finetunes* the official `lerobot/smolvla_base` checkpoint
  instead of training a VLM from random weights — training one from scratch
  isn't realistic on one GPU within the spec's 20,000-step cap, and this is
  what HuggingFace's own SmolVLA docs recommend. Both `lerobot/smolvla_base`
  and its VLM backbone's own `transformers` config/tokenizer
  (`HuggingFaceTB/SmolVLM2-500M-Video-Instruct`) are baked into the image at
  build time, so a job needs no Hub access at run time (confirmed with
  `docker run --network none`); ACT's ResNet-18 backbone is baked in the
  same way (a separate mechanism — `torch.hub`, not the HF Hub — so it
  needed its own fix once the first offline run surfaced it).
- Both images moved off the stub's `python:3.11-slim` base to
  `nvidia/cuda:12.8.1-cudnn-runtime-ubuntu24.04` + Python 3.12 (`lerobot`
  0.5+ requires it) with a CUDA 12.8 PyTorch build (matches this training
  host's driver: RTX 4090, driver 580.126.09 / CUDA 13.0, forward-compatible
  with cu12.8). `lerobot[dataset]` (`[dataset,smolvla]` for the SmolVLA
  image) is installed rather than `[training]`: both entrypoints drive their
  own loop instead of lerobot's `accelerate`/`wandb`-based `lerobot-train`
  CLI, so those extras are skipped.
- Dataloading uses `num_workers=0` (single-process) rather than lerobot's
  own default of 4: the worker's `docker run` doesn't size `/dev/shm` for
  multi-worker tensor passing (Docker's 64MB default), and GPU compute, not
  CPU dataloading, dominates step time for both policies anyway.
- **Verified on the actual RTX 4090 training host**: both images built and
  run end-to-end (`docker run --gpus all`) against a real dataset
  (`lerobot/pusht`, downloaded from the HF Hub) for a handful of real
  training steps each — real forward/backward/optimizer steps on the GPU,
  real `progress.json` updates, and a real checkpoint (ACT: ~207MB
  `model.safetensors`; SmolVLA: ~1.2GB) that `worker/checkpoint_packager.py`
  successfully zipped. Not exercised: a full-length (thousands-of-steps) run,
  or the worker's own heartbeat/timeout logic driving a real container
  (that path's plumbing — reading `progress.json`, checking exit codes — was
  already covered by the "What's genuinely tested" section above against
  the old stub, and the contract didn't change).
- **Known gap surfaced by moving to real training**: this repo's own
  dataset validation (`common/domain/policy_shapes.py`) doesn't require a
  visual feature for ACT, but `lerobot`'s real `ACTConfig.validate_features()`
  does (image *or* simulated env-state). A state-only dataset can pass this
  service's upload validation and still fail at training time with a clear
  `ValueError` — surfaced to the job as a generic "exited with code 1"
  (`worker/job_completion.py` doesn't thread container stderr into
  Firestore's `error_message`). Not fixed here; `policy_shapes.py` would
  need to require a visual feature for ACT too.

## Scope and known gaps

Deliberately left out of this pass (see the spec for what they should do):

- **React frontend** — not built.
- HF OAuth login and reCAPTCHA verification are real code, verified only
  by review — neither can be exercised without a browser (no frontend
  exists to produce a real OAuth code or reCAPTCHA token).
- **Backend deployed to Cloud Run**: live at
  `https://lerobot-backend-526282644766.asia-east1.run.app` (project
  `sstc-aiteam`, region `asia-east1` — migrated from an initial
  `us-central1` deploy, with the old service/staging-bucket/Artifact
  Registry repo all deleted, not left orphaned), talking to the real
  Firestore/GCS from earlier. Verified
  `/docs`, `/internal/check-timeouts` (real Firestore), and that the old
  default `LEROBOT_JWT_SECRET`/`LEROBOT_SCHEDULER_SHARED_SECRET` are gone
  (real random values now). Both are now sourced from Secret Manager
  (`lerobot-jwt-secret`/`lerobot-scheduler-secret`) rather than plain env
  vars, with the runtime service account granted `secretAccessor` on each
  individually — see `deploy/README.md`'s "Deployed status" for details.
  `LEROBOT_RECAPTCHA_SECRET_KEY` now lives there too (`lerobot-recaptcha-secret`),
  verified against Google's real siteverify API via a bogus-token call to
  the live `/auth/register` endpoint (got a clean 400, not a crash or an
  "invalid secret" error).
- **Cloud Scheduler provisioned**: `lerobot-check-timeouts` is `ENABLED`
  in `us-central1`, hitting the live backend's `/internal/check-timeouts`
  every 5 minutes with the real scheduler secret — see `deploy/README.md`
  for what was and wasn't independently verifiable (no Cloud Logging
  access from here to confirm Scheduler's own view of the HTTP result,
  though the identical call was independently curl-verified to work).
- **GCS bucket lifecycle rule applied**: `gs://phyai-saas-train-vla-gs`
  now carries the two rules from `deploy/gcs-lifecycle.json` (1-day
  orphaned-upload cleanup, 7-day checkpoint expiry), confirmed via `gsutil
  lifecycle get`. The actual deletions happen on GCS's own daily sweep —
  not something to sit and watch for.
- Dataset fetching (`dataset_fetcher.py`) runs synchronously inside
  `JobPoller.tick()`, blocking the poll loop for as long as the download
  takes. On a well-connected host this should comfortably fit inside the
  5-minute `initializing` timeout for the spec's 2GB dataset cap, but
  nothing currently refreshes the heartbeat *during* a long download —
  worth watching if real-world fetches turn out slower than expected.
