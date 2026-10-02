# Deployment artifacts

Reference configs for the pieces the spec calls out that aren't backend/worker
application code. The Firestore/GCS pieces *have* been verified against a real
GCP project (see `scripts/manual_test_real_gcp.py` and the README's "What's
genuinely tested" section) — review before using regardless.

## Firestore setup

1. Create the database once per project (Console → Firestore → "Create
   database", **Native mode**) — there's no API call that does this for you,
   and the client library errors with `NotFound` until it exists.
2. Grant the app's service account `roles/datastore.user` (data read/write
   only — deliberately *not* index-management rights; see step 3) and
   `roles/storage.objectAdmin` on the bucket:
   ```bash
   gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
     --member="serviceAccount:YOUR_SERVICE_ACCOUNT_EMAIL" \
     --role="roles/datastore.user"
   gsutil iam ch serviceAccount:YOUR_SERVICE_ACCOUNT_EMAIL:roles/storage.objectAdmin gs://YOUR_BUCKET_NAME
   ```
3. Two of `FirestoreJobRepository`'s queries combine a filter with
   `order_by` on a different field, which Native-mode Firestore requires a
   composite index for — `firestore.indexes.json` documents the two needed
   (`jobs`: user_id+created_at, and status+created_at). The first time you
   run either query without them, the error message includes a direct
   "create this index" console link — that's the easiest way to create
   them (uses your own admin credentials, not the app's service account,
   which intentionally lacks `datastore.indexAdmin`/`owner`). Each takes a
   minute or two to finish building after creation.

## Manual end-to-end testing against real GCP

`scripts/manual_test_real_gcp.py` (see the main README) runs the backend +
worker against real Firestore/GCS instead of in-memory fakes, with only
reCAPTCHA/HF OAuth faked (no browser available to produce a real
token/code). It writes real data (a demo user, job docs, an uploaded
checkpoint) and does not clean up after itself — see the script's own
printed reminder, or delete the `users`/`jobs` docs and any
`checkpoints/`/`uploads/` objects by hand afterward.

## Backend (Cloud Run)

The root `Dockerfile` packages `backend.main:app` (multi-stage, `uv sync
--frozen --no-dev`, runs as a non-root user, listens on `$PORT` per Cloud
Run's convention). Built and run locally against both fake and real
adapters to confirm it boots and — with the real service account key
mounted in — correctly reaches real Firestore (through the composite
indexes) and GCS from inside the container.

Deploying it is intentionally **not** done with the app's own runtime
service account: that account only has `roles/datastore.user` +
`roles/storage.objectAdmin` (what the *running* app needs), not
Cloud Build/Artifact Registry/Cloud Run admin rights (what *deploying* it
needs) — keep those separate. Run this yourself with your own
(more-privileged) `gcloud` session:

```bash
gcloud run deploy lerobot-backend \
  --source . \
  --region YOUR_REGION \
  --project YOUR_PROJECT_ID \
  --service-account YOUR_APP_SERVICE_ACCOUNT_EMAIL \
  --allow-unauthenticated \
  --set-env-vars LEROBOT_USE_FAKE_ADAPTERS=false,LEROBOT_GCP_PROJECT_ID=YOUR_PROJECT_ID,LEROBOT_FIRESTORE_DATABASE_ID=YOUR_DATABASE_ID,LEROBOT_GCS_BUCKET=YOUR_BUCKET_NAME
```

`--source .` has Cloud Build build the `Dockerfile` remotely — no local
`docker push` needed. `--allow-unauthenticated` matches the spec's "public
service" positioning (section 1); tighten it if that changes.
`LEROBOT_JWT_SECRET`/`LEROBOT_SCHEDULER_SHARED_SECRET`/
`LEROBOT_RECAPTCHA_SECRET_KEY`/`LEROBOT_HF_OAUTH_CLIENT_SECRET` are left out
of the example above on purpose — create them in Secret Manager and attach
with `--update-secrets ENV_VAR=SECRET_NAME:latest` (see "Deployed status"
below for the exact commands used) rather than plain `--set-env-vars`,
since they're credentials, not config. The running service account needs
`roles/secretmanager.secretAccessor` on each secret (grant it per-secret,
not project-wide) in addition to what's needed to create the secret in the
first place (`roles/secretmanager.admin` on the deploying identity). No
IAM binding is needed for the running service to reach
Firestore/GCS beyond what's already on `YOUR_APP_SERVICE_ACCOUNT_EMAIL`
(see "Firestore setup" above) — Cloud Run just runs the container *as*
that service account.

**Deployed status**: live at `https://lerobot-backend-526282644766.asia-east1.run.app`
(project `sstc-aiteam`, region `asia-east1` — migrated from an initial
`us-central1` deploy; the old service, its Cloud Build staging bucket
`run-sources-sstc-aiteam-us-central1`, and its `cloud-run-source-deploy`
Artifact Registry repo were all deleted rather than left orphaned).
Redeployed (`lerobot-backend-00004-zmp`) to pick up the ACT
visual-feature-or-`observation.environment_state` validation fix
(`common/domain/policy_shapes.py`, commit `d3987bb`) — the only one of
three recent bug fixes that touches backend code (the disk-leak-on-cancel
and container-log-surfacing fixes are worker-only and live on the GPU
host instead, not Cloud Run). A bare `gcloud run deploy --source .` with
no `--set-env-vars`/`--set-secrets` carried forward the existing
Secret-Manager-backed env vars unchanged — confirmed on the new revision
(all three secrets still `valueFrom.secretKeyRef`, not plain values) and
re-verified end-to-end (`/docs` → 200, `/internal/check-timeouts` with
the real secret → 200).
`LEROBOT_JWT_SECRET` and `LEROBOT_SCHEDULER_SHARED_SECRET` are now sourced
from Secret Manager (secrets `lerobot-jwt-secret` and
`lerobot-scheduler-secret`, both `automatic` replication) via
`--update-secrets`, not plain `--set-env-vars` — confirmed on the live
revision (`spec.template.spec.containers[0].env[].valueFrom.secretKeyRef`)
and re-verified end-to-end (`/docs` → 200, `/internal/check-timeouts` with
the real secret → 200). The runtime service account was granted
`roles/secretmanager.secretAccessor` on each secret individually (not
project-wide) to keep it least-privilege; creating/updating the secrets
themselves needed a one-off `roles/secretmanager.admin` grant on the
deploying identity, same separation as the Cloud Run/Cloud Build grants
above.

`LEROBOT_RECAPTCHA_SECRET_KEY` was added the same way once a real
reCAPTCHA v3 secret key existed (secret `lerobot-recaptcha-secret`,
`secretAccessor` granted to the runtime SA on that secret only). Verified
by calling `POST /auth/register` on the live service with a deliberately
bogus token: got a clean `400 {"detail":"reCAPTCHA verification
failed"}` from Google's real siteverify API — proves the secret key itself
is valid and reachable, not just that the wiring didn't crash. The
reCAPTCHA site was registered for `localhost` only, since no frontend
domain exists yet; add the real domain in the reCAPTCHA admin console
once the frontend is deployed.

## Worker host (systemd)

1. Copy `worker.env.example` to `/etc/lerobot-worker/worker.env`, fill in real
   values (bucket name, GCP service account key path — spec section 2 says
   the worker authenticates with a service account key file, not ADC).
2. Copy `lerobot-worker.service` to `/etc/systemd/system/`.
3. Create the `lerobot-worker` user/group and add it to `docker` (needed for
   `/var/run/docker.sock` access):
   ```bash
   sudo useradd --system --create-home lerobot-worker
   sudo usermod -aG docker lerobot-worker
   ```
4. `sudo systemctl daemon-reload && sudo systemctl enable --now lerobot-worker`

`Restart=always` (spec section 2) is set in the unit; the worker's own lock
file (`worker/lock.py`) keeps a second instance from ever running alongside a
restarted one. The unit's `RuntimeDirectory=lerobot-worker` creates
`/run/lerobot-worker/` (owned by the `lerobot-worker` user) for that lock
file to live in — `/run` itself is `root:root 0755`, so a non-root worker
can't create a lock file directly under `/var/run`/`/run`, which is exactly
what the first real run on a systemd host caught: it crash-looped
(`PermissionError` out of `WorkerLock.acquire()`) until `RuntimeDirectory`
was added and `WorkerSettings.lock_file_path`'s default moved off
`/var/run/lerobot-worker.lock`.

**Deployed status**: staged and started on the training host (project
`sstc-aiteam`, Firestore database `phyai-saas-train-vla-cf`, bucket
`phyai-saas-train-vla-gs`) — app deployed to `/opt/lerobot-training-service`,
`lerobot-worker` user created and in the `docker` group, service account key
at `/etc/lerobot-worker/gcp-service-account.json` (mode 600, owned by
`lerobot-worker`), `worker.env` at mode 640 (`root:lerobot-worker`). The
`RuntimeDirectory` crash above was hit and fixed on this exact host before
the service came up clean.

**A second, more serious bug came out of that same first run**: on startup,
`DockerClient.list_running_container_ids()` returned *every* running
container on the host, not just this service's own -- and
`worker/orphan_reconciler.py` kills anything that list contains that isn't a
tracked job (spec section 4's "at most one training container" guarantee).
On this host that killed a real, unrelated `redis` container that had
nothing to do with this service (recovered with `docker start redis`, since
`kill` doesn't remove the container). Fixed by scoping
`list_running_container_ids()` to containers carrying the
`LEROBOT_JOB_ID_LABEL` label (`lerobot.job_id`) that `worker/job_poller.py`
already puts on every container it starts -- see
`tests/worker/test_orphan_reconciler.py::test_unrelated_container_without_our_label_is_left_alone`
for the regression test, and `common/ports/docker_client.py`'s module
docstring for the full story. Re-verified against this host's real Docker
daemon after the fix: an unlabeled container is left running, a labeled one
is not. **This means the spec's assumption that the training host is fully
dedicated to this service doesn't actually hold on this machine** — if
anything else here runs long-lived Docker containers, review this before
relying on `Restart=always` cycling the worker (e.g. after a crash or a
`lock_file_path`-style config change) to never touch them.

## GCS bucket lifecycle rule (spec sections 3 and 7)

`gcs-lifecycle.json` implements:
- Orphaned upload zips (`uploads/` prefix, never confirmed) — deleted after
  1 day. `worker/dataset_fetcher.py` also deletes a *confirmed* upload's
  object itself right after extracting it, so in normal operation this rule
  is mostly a backstop for genuinely abandoned uploads, not the primary
  cleanup path.
- Checkpoint downloads (`checkpoints/` prefix) — deleted after 7 days,
  matching the signed download URL's expiry.

Apply with:
```bash
gsutil lifecycle set gcs-lifecycle.json gs://<your-bucket-name>
```

**Deployed status**: applied to `gs://phyai-saas-train-vla-gs`; confirmed
with `gsutil lifecycle get` that the bucket's rule matches this file
exactly. Actual deletions happen on GCS's own daily lifecycle sweep, which
isn't something to wait around and verify here — the config being live is
the checkable part.

## Cloud Scheduler (spec section 4)

Not included as a file here (it's a single `gcloud` command, not a config
file worth version-controlling on its own). Point it at the backend's
`POST /internal/check-timeouts` endpoint every 5 minutes, with the
`X-Scheduler-Secret` header set to `Settings.scheduler_shared_secret`:

```bash
gcloud scheduler jobs create http lerobot-check-timeouts \
  --location YOUR_REGION \
  --schedule="*/5 * * * *" \
  --uri="https://<backend-cloud-run-url>/internal/check-timeouts" \
  --http-method=POST \
  --headers="X-Scheduler-Secret=<same value as LEROBOT_SCHEDULER_SHARED_SECRET>"
```

Needs the Cloud Scheduler API enabled and `roles/cloudscheduler.admin` on
whichever identity creates the job (same pattern as the Cloud Run
permissions above — not something the app's own runtime service account
should have either).

**Deployed status**: `lerobot-check-timeouts` exists in `us-central1`
(the job's own location — doesn't need to match the Cloud Run region it
targets), project `sstc-aiteam`, `state: ENABLED`, targeting the live
Cloud Run URL above (updated via `gcloud scheduler jobs update` when the
backend moved from `us-central1` to `asia-east1`). `gcloud scheduler jobs
run lerobot-check-timeouts` was used to trigger it once manually and
completed without error; the deploying identity doesn't have Cloud
Logging access to confirm the resulting HTTP status Cloud Scheduler
itself saw, but the identical URL+header combination was independently
verified via `curl` to return `200
{"failed_job_ids":[]}` (see "Backend (Cloud Run)" above), so the scheduled
calls should succeed the same way every 5 minutes.
