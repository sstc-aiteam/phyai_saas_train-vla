from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LEROBOT_", env_file=".env", extra="ignore")

    jwt_secret: str = "dev-secret-change-me"
    scheduler_shared_secret: str = "dev-scheduler-secret-change-me"
    gcs_bucket: str = "lerobot-training-service-dev"
    # Firestore supports multiple named databases per project; "(default)"
    # is the literal name of the one auto-created if you never name one.
    firestore_database_id: str = "(default)"
    gcp_project_id: str | None = None  # None lets the client library infer it (e.g. from ADC)
    recaptcha_secret_key: str = ""
    min_captcha_score: float = 0.5
    hf_oauth_client_id: str = ""
    hf_oauth_client_secret: str = ""
    use_fake_adapters: bool = True  # flip to False once GCP/HF credentials are configured
    # Only used when use_fake_adapters is true: where InMemoryObjectStorage's
    # dev-storage URLs should point back to. Override if serving on a
    # different host/port than the plain `uvicorn` default.
    dev_storage_base_url: str = "http://localhost:8000"
    # Comma-separated browser origins allowed to call this API (the frontend
    # is served from a different origin than this API, e.g. Firebase
    # Hosting, so CORS is required). Defaults to the Vite dev server.
    cors_allowed_origins: str = "http://localhost:5173"


def get_settings() -> Settings:
    return Settings()
