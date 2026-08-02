# Phase 0 — Multi-Tenant Foundation & Hardening

This phase turns the single-association Bayan POS into a **multi-tenant** backend
where many associations share one database safely, and hardens the security
basics. It is a drop-in evolution: the existing feature routers
(`products`, `sales`, `donations`, `reports`, `settings`) were **not changed** —
they became tenant-safe automatically.

Verified in a real PostgreSQL 16 instance: **4/4 isolation tests pass**
(API-layer isolation, DB-layer RLS read isolation, cross-tenant write blocked,
fail-closed with no tenant set).

---

## What changed

**New files**
- `config.py` — all settings from environment (`pydantic-settings`); no secrets in code.
- `tenancy.py` — JWT helpers (`get_secret_key`, `decode_token`, `extract_token`).
- `alembic.ini`, `migrations/` — schema migrations (replaces the fragile startup `ALTER TABLE`).
- `migrations/versions/0001_baseline_multitenant.py` — creates the schema, grants the
  app role, and applies **Row-Level Security** on every tenant table.
- `tests/test_isolation.py` — automated proof of isolation.
- `.env.example`, `requirements-dev.txt`, `.gitignore`
- `deploy/00_roles.sql`, `deploy/Caddyfile`, `deploy/bayan-pos.service`

**Rewritten**
- `database.py` — PostgreSQL engine; new `Tenant` + `TenantSettings` models; every
  existing table gets a `tenant_id`; `get_db` pins each request's DB connection to
  the caller's tenant.
- `routers/auth.py` — env-based secret; **tenant-aware login**; JWT stored in an
  **httpOnly cookie**; `/logout`; `must_change_password`.
- `main.py` — CORS allow-list (no `*`); lifespan bootstrap of the first tenant + admin;
  removed the SQLite migration block; added `/health`.
- `requirements.txt` — added SQLAlchemy 2/Alembic/psycopg2/pydantic-settings; pinned
  `bcrypt==4.0.1` (see note below).
- `frontend/src/services/api.js` — uses the httpOnly cookie (`withCredentials`) instead
  of a localStorage token; adds `logout` and an optional `tenant` on login.

---

## How isolation works (simple, secure, light)

Two independent layers, so a bug in one is caught by the other:

1. **Application** — on every request, `get_db` reads the tenant id from the JWT
   (cookie or `Authorization: Bearer`) and runs `SET app.current_tenant = <id>` on the
   connection before any query.
2. **Database (PostgreSQL RLS)** — every tenant table has a policy
   `USING (tenant_id = current_setting('app.current_tenant'))`. The app connects as a
   **non-superuser role** (`pos_app`), so the policy is always enforced. If the variable
   is unset, queries return **zero rows** (fail-closed) rather than leaking data.

`tenant_id` is filled automatically by a column `DEFAULT` that reads the same session
variable — which is why the existing routers needed no edits. A `WITH CHECK` clause
blocks writing a row for any other tenant.

The `tenants` table itself has no RLS (it is the directory used to resolve a tenant at
login).

---

## Run locally (development)

```bash
# 1) PostgreSQL running locally, then create roles + db (edit passwords):
sudo -u postgres psql -f deploy/00_roles.sql

# 2) Python env
cd backend
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# 3) Config
cp .env.example .env       # then edit: set SECRET_KEY, DATABASE_URL, COOKIE_SECURE=False for http

# 4) Migrate (APP_DB_ROLE must match the app role used by RLS grants)
APP_DB_ROLE=pos_app alembic upgrade head

# 5) Run
uvicorn main:app --reload --port 8000
```

Run the isolation test (expects the migrated `pos` db):

```bash
pytest -q tests/test_isolation.py
```

---

## Deploy on Debian 12 (bare-metal — the lightest path)

```bash
# 1) Packages
sudo apt update
sudo apt install -y postgresql python3-venv python3-pip caddy

# 2) Roles + database  (edit the passwords first)
sudo -u postgres psql -v owner_pw="'STRONG_OWNER'" -v app_pw="'STRONG_APP'" -f deploy/00_roles.sql

# 3) App user + code
sudo useradd -r -m -d /srv/bayan-pos bayan
sudo -u bayan git clone <your repo> /srv/bayan-pos   # or copy the folder
cd /srv/bayan-pos/backend
sudo -u bayan python3 -m venv .venv
sudo -u bayan .venv/bin/pip install -r requirements.txt

# 4) Config
sudo -u bayan cp .env.example .env
sudo -u bayan nano .env          # SECRET_KEY (openssl rand -hex 32), DB urls, CORS_ORIGINS, COOKIE_SECURE=True, BOOTSTRAP_ADMIN_PASSWORD

# 5) Migrate
sudo -u bayan bash -c 'set -a; . .env; APP_DB_ROLE=pos_app .venv/bin/alembic upgrade head'

# 6) Build the frontend (served by FastAPI from ../frontend/dist)
cd /srv/bayan-pos/frontend && sudo -u bayan npm ci && sudo -u bayan npm run build

# 7) Service + reverse proxy
sudo cp /srv/bayan-pos/backend/deploy/bayan-pos.service /etc/systemd/system/
sudo systemctl enable --now bayan-pos
sudo cp /srv/bayan-pos/backend/deploy/Caddyfile /etc/caddy/Caddyfile   # edit the domain
sudo systemctl reload caddy

# 8) Host hardening
sudo ufw allow 22,80,443/proto tcp && sudo ufw enable
sudo apt install -y fail2ban unattended-upgrades
```

Nightly backup (cron): `pg_dump pos | gzip > /backups/pos-$(date +\%F).sql.gz`
(then sync to OCI Object Storage).

> **Docker Compose alternative:** if you'd rather containerize (app + postgres + caddy),
> the app code is identical — only the packaging differs. Say the word and I'll add a
> `docker-compose.yml` + `Dockerfile`.

---

## Security notes

- Change the seeded admin password immediately; it is flagged `must_change_password`
  (enforcing the change in the UI is a small Phase 1 item).
- `SECRET_KEY` is **required** in production — the app refuses to start without it.
- Keep `COOKIE_SECURE=True` in production (HTTPS only).
- The app must connect as a **non-superuser** role (`pos_app`) or RLS won't apply.

## Notes / gotchas

- **`bcrypt==4.0.1` is pinned** on purpose: `passlib 1.7.4` breaks on bcrypt ≥ 4.1
  ("password cannot be longer than 72 bytes"). The pin avoids it.
- **UTF-8 database**: the migration/app assume a UTF-8 database (for Arabic). Debian 12's
  default locale produces this; `deploy/00_roles.sql` creates the db as UTF-8 explicitly.

## Next — Phase 1

Locations → registers → user↔location mapping, and register selection at the POS.
