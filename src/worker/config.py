from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LEROBOT_WORKER_", env_file=".env", extra="ignore")

    lock_file_path: str = "/var/run/lerobot-worker.lock"
    hf_cache_dir: str = "/var/lib/lerobot-worker/hf-cache"
    hf_cache_max_bytes: int = 20 * 1024**3  # 20GB, spec section 5
    workdir: str = "/var/lib/lerobot-worker/jobs"
    tmp_stale_after_seconds: int = 60 * 60  # 1 hour, spec section 5
    poll_interval_seconds: float = 5.0
    act_image: str = "lerobot-train-act:latest"
    smolvla_image: str = "lerobot-train-smolvla:latest"
    gcs_bucket: str = "lerobot-training-service-dev"
