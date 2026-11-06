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
    # Connections per app worker (stress test: 5+10 ran out at ~160 simultaneous
    # logins). Keep workers × (size + overflow) well under PostgreSQL's
    # max_connections (default 100): 2 workers × 20 + console 20 = 60.
    db_pool_size: int = 10
    db_max_overflow: int = 10
    db_pool_timeout: int = 15

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

    # --- Private files (bank-transfer proofs). NOT served as static files. ---
    private_storage_dir: str = "storage"
    proof_max_bytes: int = 5 * 1024 * 1024

    # --- Platform console (Release 2b, separate process on its own subdomain) ---
    # Optional own secret; when empty, keys are derived from SECRET_KEY.
    # NOTE: the TOTP secrets are encrypted with this key: changing it means
    # every platform admin must re-enrol (python manage.py platform-admin reset-mfa).
    platform_secret_key: str = ""
    platform_cookie_name: str = "platform_session"
    platform_session_minutes: int = 30          # idle timeout (sliding)
    platform_session_max_hours: int = 8        # absolute cap, then log in again
    platform_max_login_attempts: int = 5
    platform_lockout_minutes: int = 15
    platform_issuer: str = "SahlPOS Platform"   # label shown in the authenticator app

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
