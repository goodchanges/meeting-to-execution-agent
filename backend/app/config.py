from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", hide_input_in_errors=True
    )

    app_env: Literal["development", "test", "staging", "production"] = "development"
    db_path: Path = Path("data/meetflow.sqlite")
    secret_key: SecretStr = SecretStr("local-development-only")
    public_url: str = "http://localhost:8000"
    cors_origins: list[str] = []
    trusted_proxies: list[str] = []
    app_version: str = "dev"
    frontend_dir: Path = Path("frontend/dist")
    session_hours: int = Field(default=24, ge=1, le=168)
    max_upload_bytes: int = Field(default=1_048_576, ge=64, le=10_485_760)
    max_segments: int = Field(default=2000, ge=1, le=10_000)
    ai_mode: Literal["live", "demo"] = "live"
    llm_api_key: SecretStr = SecretStr("")
    llm_model: str = "gpt-6-luna"
    max_input_tokens: int = Field(default=16000, ge=100, le=100_000)
    max_output_tokens: int = Field(default=4096, ge=16, le=10_000)
    ai_timeout: float = Field(default=25, gt=0, le=45)
    ai_user_monthly_call_cap: int = 100
    ai_global_monthly_call_cap: int = 1000
    memory_candidates: int = Field(default=8, ge=1, le=30)
    confidence_threshold: float = Field(default=0.7, ge=0, le=1)
    github_token: SecretStr = SecretStr("")
    scheduler_enabled: bool = True
    reminder_days: int = Field(default=2, ge=0, le=30)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    smtp_sender: str = ""
    dev_outbox: Path = Path("dev-outbox")
    slow_request_ms: int = 1000
    metrics_token: SecretStr = SecretStr("")
    rate_general: int = Field(default=120, ge=1)
    rate_login: int = Field(default=5, ge=1)
    rate_reset: int = Field(default=3, ge=1)
    rate_upload: int = Field(default=10, ge=1)
    rate_ai: int = Field(default=10, ge=1)
    rate_github: int = Field(default=30, ge=1)

    @property
    def secure(self) -> bool:
        return self.app_env in {"staging", "production"}

    @model_validator(mode="after")
    def validate_deployment(self):
        origin = urlsplit(self.public_url)
        if (
            origin.scheme not in {"http", "https"}
            or not origin.hostname
            or origin.username
            or origin.path not in {"", "/"}
            or origin.query
            or origin.fragment
        ):
            raise ValueError(
                "PUBLIC_URL must be an HTTP(S) origin without credentials or a path."
            )
        if "*" in self.cors_origins:
            raise ValueError("CORS requires an explicit origin allowlist")
        if self.secure and (
            len(self.secret_key.get_secret_value()) < 32
            or not self.public_url.startswith("https://")
        ):
            raise ValueError("Set a strong SECRET_KEY and HTTPS PUBLIC_URL")
        return self
