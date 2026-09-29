# Deployment artifacts

Reference configs for the pieces the spec calls out that aren't backend/worker
application code. The systemd unit hasn't been applied/tested against a real
systemd host. The Firestore/GCS pieces *have* been verified against a real
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
restarted one.

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

## Cloud Scheduler (spec section 4)

Not included as a file here (it's a single `gcloud` command, not a config
file worth version-controlling on its own). Point it at the backend's
`POST /internal/check-timeouts` endpoint every 5 minutes, with the
`X-Scheduler-Secret` header set to `Settings.scheduler_shared_secret`:

```bash
gcloud scheduler jobs create http lerobot-check-timeouts \
  --schedule="*/5 * * * *" \
  --uri="https://<backend-cloud-run-url>/internal/check-timeouts" \
  --http-method=POST \
  --headers="X-Scheduler-Secret=<same value as LEROBOT_SCHEDULER_SHARED_SECRET>"
```
