from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LEROBOT_", env_file=".env", extra="ignore")

    jwt_secret: str = "dev-secret-change-me"
    scheduler_shared_secret: str = "dev-scheduler-secret-change-me"
    gcs_bucket: str = "lerobot-training-service-dev"
    recaptcha_secret_key: str = ""
    min_captcha_score: float = 0.5
    hf_oauth_client_id: str = ""
    hf_oauth_client_secret: str = ""
    use_fake_adapters: bool = True  # flip to False once GCP/HF credentials are configured


def get_settings() -> Settings:
    return Settings()
