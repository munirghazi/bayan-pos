"""Pytest bootstrap: run the whole suite against a DEDICATED, throwaway
database that is reset before every session — so tests never touch (or pollute)
your dev/prod data, and every run starts from a clean, migrated schema.

The test DB name is the app DB name + "_test" (e.g. pos -> pos_test). Create it
once (see the error message below if it's missing); this file wipes and
re-migrates its schema on each run.
"""
import os
import re
from pathlib import Path


def _load_env(path=".env"):
    env = {}
    p = Path(path)
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def _split(url: str):
    """Return (base_with_slash, dbname, query) — query split off first so a
    '/' inside it (e.g. ?host=/tmp) can't be mistaken for the db separator."""
    if "?" in url:
        head, q = url.split("?", 1)
        query = "?" + q
    else:
        head, query = url, ""
    base, _, db = head.rpartition("/")
    return base + "/", db, query


def _to_test_url(url: str) -> str:
    base, db, query = _split(url)
    if db and not db.endswith("_test"):
        db = db + "_test"
    return f"{base}{db}{query}"


def _dbname(url: str) -> str:
    return _split(url)[1]


_env = _load_env()
_app_url = os.environ.get("DATABASE_URL", _env.get("DATABASE_URL", ""))
_mig_url = os.environ.get("MIGRATION_DATABASE_URL", _env.get("MIGRATION_DATABASE_URL", _app_url))

TEST_APP_URL = _to_test_url(_app_url)
TEST_MIG_URL = _to_test_url(_mig_url)

# Point the app + tests at the test DB BEFORE anything imports config/database.
os.environ["DATABASE_URL"] = TEST_APP_URL
os.environ["MIGRATION_DATABASE_URL"] = TEST_MIG_URL
os.environ.setdefault("APP_DB_ROLE", "pos_app")
os.environ.setdefault("COOKIE_SECURE", "False")

# Safety net: never operate on a database whose name isn't a *_test database.
_name = _dbname(TEST_APP_URL)
assert _name.endswith("_test"), f"Refusing to run tests against non-test DB '{_name}'"


def _reset_and_migrate():
    import psycopg2
    from alembic import command
    from alembic.config import Config

    dsn = TEST_MIG_URL.replace("+psycopg2", "")
    try:
        conn = psycopg2.connect(dsn)
    except psycopg2.OperationalError as e:
        raise RuntimeError(
            f"\nTest database '{_name}' is not reachable. Create it once:\n\n"
            f"  sudo -u postgres psql -c \"CREATE DATABASE {_name} OWNER pos_owner "
            f"ENCODING 'UTF8' TEMPLATE template0 LC_COLLATE 'C' LC_CTYPE 'C';\" "
            f"-c \"GRANT CONNECT ON DATABASE {_name} TO pos_app;\"\n"
            f"  sudo -u postgres psql -d {_name} -c \"ALTER SCHEMA public OWNER TO pos_owner;\" "
            f"-c \"GRANT USAGE ON SCHEMA public TO pos_app;\"\n"
        ) from e
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("DROP SCHEMA IF EXISTS public CASCADE")
    cur.execute("CREATE SCHEMA public")
    cur.execute(f"GRANT USAGE ON SCHEMA public TO {os.environ['APP_DB_ROLE']}")
    conn.close()

    command.upgrade(Config("alembic.ini"), "head")


_reset_and_migrate()
