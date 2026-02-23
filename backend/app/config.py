from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Dev-only fallback — NEVER used in production.
_DEV_MASTER_KEY_SECRET = "dev-insecure-do-not-use-in-production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    database_url: str
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expiry_seconds: int = 3600
    environment: str = "development"

    # AES-256-GCM master secret used for per-user key derivation (HKDF-SHA256).
    # Production: must be set via secret manager; generate with `openssl rand -base64 32`.
    # Development: falls back to a weak insecure default so the test suite can run.
    # The application MUST NOT start in production if this is empty or missing.
    master_key_secret: str = Field(default=_DEV_MASTER_KEY_SECRET)

    @field_validator("master_key_secret", mode="after")
    @classmethod
    def _validate_master_key_secret(cls, v: str, info) -> str:
        # Access other fields via info.data; environment may not be set yet if
        # validation order is alphabetical, so we check explicitly.
        env = info.data.get("environment", "development")
        if env != "development" and (not v or v == _DEV_MASTER_KEY_SECRET):
            raise ValueError(
                "MASTER_KEY_SECRET must be set to a strong random secret in production. "
                "Generate one with: openssl rand -base64 32"
            )
        return v

    @property
    def is_dev(self) -> bool:
        return self.environment == "development"


settings = Settings()
