from pathlib import Path
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "staging", "production"] = "development"
    db_path: Path = Path("data/meetflow.sqlite")
    secret_key: SecretStr = SecretStr("local-development-only")
    public_url: str = "http://localhost:8000"
    cors_origins: list[str] = []
    trusted_proxies: list[str] = []
    app_version: str = "dev"
    frontend_dir: Path = Path("frontend/dist")
    session_hours: int = 24
    max_upload_bytes: int = 1_048_576
    max_segments: int = 2000
    ai_mode: Literal["live", "demo"] = "live"
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = "gpt-6-luna"
    max_input_tokens: int = 16000
    max_output_tokens: int = 4096
    ai_timeout: float = 25
    ai_user_monthly_call_cap: int = 100
    ai_global_monthly_call_cap: int = 1000
    memory_candidates: int = 8
    confidence_threshold: float = 0.7
    github_token: SecretStr = SecretStr("")
    scheduler_enabled: bool = True
    reminder_days: int = 2
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_sender: str = ""
    dev_outbox: Path = Path("dev-outbox")
    slow_request_ms: int = 1000
    metrics_token: SecretStr = SecretStr("")
    rate_general: int = 120
    rate_login: int = 5
    rate_reset: int = 3
    rate_upload: int = 10
    rate_ai: int = 10
    rate_github: int = 30

    @property
    def secure(self) -> bool:
        return self.app_env in {"staging", "production"}

    @model_validator(mode="after")
    def validate_deployment(self):
        if "*" in self.cors_origins:
            raise ValueError("CORS requires an explicit origin allowlist")
        if self.secure and (
            len(self.secret_key.get_secret_value()) < 32
            or not self.public_url.startswith("https://")
        ):
            raise ValueError("Set a strong SECRET_KEY and HTTPS PUBLIC_URL")
        return self
