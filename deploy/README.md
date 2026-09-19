# Deployment artifacts

Reference configs for the pieces the spec calls out that aren't backend/worker
application code. None of these have been applied or tested against real
GCP/systemd in this environment — review before using.

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
