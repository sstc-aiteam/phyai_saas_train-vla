from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LEROBOT_WORKER_", env_file=".env", extra="ignore")

    # Under /run/lerobot-worker/, not /var/run directly: that subdirectory is
    # created (owned by this process's own user) by the systemd unit's
    # `RuntimeDirectory=lerobot-worker` -- /run itself is root:root 0755, so
    # a non-root worker can't create a lock file there directly.
    lock_file_path: str = "/run/lerobot-worker/lerobot-worker.lock"
    hf_cache_dir: str = "/var/lib/lerobot-worker/hf-cache"
    hf_cache_max_bytes: int = 20 * 1024**3  # 20GB, spec section 5
    workdir: str = "/var/lib/lerobot-worker/jobs"
    tmp_stale_after_seconds: int = 60 * 60  # 1 hour, spec section 5
    poll_interval_seconds: float = 5.0
    act_image: str = "lerobot-train-act:latest"
    smolvla_image: str = "lerobot-train-smolvla:latest"
    gcs_bucket: str = "lerobot-training-service-dev"
    # Firestore supports multiple named databases per project; "(default)"
    # is the literal name of the one auto-created if you never name one.
    firestore_database_id: str = "(default)"
    gcp_project_id: str | None = None  # None lets the client library infer it (e.g. from ADC)
    # Safe-by-default opposite of backend Settings.use_fake_adapters: a
    # deployed worker touches real Docker + a real GPU, so accidentally
    # running it in fake mode should require an explicit opt-in, not be
    # the default the way it is for a quick local `uvicorn` smoke test.
    use_fake_adapters: bool = False
    # Real deployments always train on the GPU; only manual/local testing
    # on a machine without one needs to turn this off.
    use_gpu: bool = True
