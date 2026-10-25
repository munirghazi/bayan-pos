"""Centralised, environment-driven configuration (no secrets in code)."""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"

    # --- Database ---
    # Runtime connection uses a NON-superuser, NON-owner role so RLS applies.
    database_url: str = "postgresql+psycopg2://pos_app:app_pw@localhost:5432/pos"
    # Migrations run as the table owner (may differ from the app role).
    migration_database_url: str | None = None

    # --- Auth / JWT ---
    secret_key: str = ""          # REQUIRED in production; auto-generated in dev
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480
    max_login_attempts: int = 5
    lockout_minutes: int = 15

    # --- Cookies (httpOnly session token) ---
    cookie_name: str = "access_token"
    cookie_secure: bool = True     # set False only for local http dev
    cookie_samesite: str = "lax"
    cookie_domain: str | None = None

    # --- CORS (comma-separated allow-list; never '*') ---
    cors_origins: str = "http://localhost:5173"

    # --- First-run bootstrap ---
    bootstrap_tenant_slug: str = "bayan"
    bootstrap_tenant_name: str = "جمعية بيان"
    bootstrap_admin_username: str = "admin"
    bootstrap_admin_password: str = ""   # if empty, admin is NOT auto-seeded

    # --- Email delivery (SMTP). Email is disabled until smtp_host is set. ---
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_from_name: str = "Bayan POS"
    smtp_tls: bool = True

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
