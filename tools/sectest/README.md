# Security + stress test kit

| Script | What | Where it may run |
|---|---|---|
| `security_suite.py` | 68 application checks: tenant isolation, logins/roles, console 2FA, uploads, business rules, injection, headers | local copy **any time**; live **after the Oracle notice** |
| `stress_test.py` | 20 concurrent cashiers, peak rush, breaking point, invoice-number integrity | **local copy only** — Oracle forbids load testing any OCI server (the script refuses `roaa.sa`) |
| `external_checks.sh` | ports, TLS, headers, exposed files — from outside | live, **after the Oracle notice** |
| `server_checks.sh` | SSH, firewall, updates, `.env`, PostgreSQL/RLS, backups — read-only, on the server | live, any time (it's a configuration review, not a test) |
| `setup_local.py` | creates test tenants/users on a LOCAL copy (refuses production) | local only |

---

## Part 1 — Local copy on the laptop (start today)

Everything runs in a **separate clone with its own database**, so your project folder and its `.env` are not touched.

### 1. One-time setup

```bash
sudo apt install -y postgresql python3-venv nmap curl openssl
git clone ~/"Development/POS for charity" ~/bayan-sectest
cd ~/bayan-sectest/backend

# own virtualenv outside the repo (the repo's tracked .venv is not used)
python3 -m venv ~/.venvs/bayan-sectest
~/.venvs/bayan-sectest/bin/pip install -r requirements.txt httpx

# database roles + database (local passwords, local only)
sudo -u postgres psql -v owner_pw="'owner_local'" -v app_pw="'app_local'" -f deploy/00_roles.sql

cat > .env <<'EOF'
ENVIRONMENT=development
DATABASE_URL=postgresql+psycopg2://pos_app:app_local@127.0.0.1:5432/pos
MIGRATION_DATABASE_URL=postgresql+psycopg2://pos_owner:owner_local@127.0.0.1:5432/pos
SECRET_KEY=local-sectest-secret-key-0123456789abcdef
COOKIE_SECURE=False
BOOTSTRAP_ADMIN_PASSWORD=admin12345
EOF

APP_DB_ROLE=pos_app ~/.venvs/bayan-sectest/bin/alembic upgrade head
```

### 2. Each test session

Terminal 1 — start both processes (like production: 2 workers + the console):

```bash
cd ~/bayan-sectest/backend
~/.venvs/bayan-sectest/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --workers 2 &
~/.venvs/bayan-sectest/bin/uvicorn platform_main:app --host 127.0.0.1 --port 8001 &
sleep 5 && curl -s localhost:8000/health && curl -s localhost:8001/health
```

Prepare the test data (safe to repeat; refuses to run if `ENVIRONMENT=production`):

```bash
~/.venvs/bayan-sectest/bin/python ../tools/sectest/setup_local.py
```

### 3. Security suite (≈ 1 minute)

```bash
cd ~/bayan-sectest/tools/sectest
~/.venvs/bayan-sectest/bin/python security_suite.py --config config.local.json
```

Expected: `PASS 68 FAIL 0 WARN 0`. A report `security-report-local-….md` is written next to the config.

### 4. Stress test (≈ 10 minutes for everything)

```bash
~/.venvs/bayan-sectest/bin/python stress_test.py --config config.local.json                 # all phases
~/.venvs/bayan-sectest/bin/python stress_test.py --config config.local.json --phase realistic --seconds 300
~/.venvs/bayan-sectest/bin/python stress_test.py --config config.local.json --phase breaking --ramp 20,40,80,160
```

Read the results:
- **realistic** (20 cashiers at a normal pace): `errors 0`, `sale p95` under ~500 ms.
- **peak** (20 cashiers, no pause = a rush far beyond a real shop): no errors; slower is fine.
- **breaking**: where p95 passes 2 s or errors start. Above the limit the system must answer **503 "النظام مشغول"**, never 500.
- **integrity**: must always say `unique and gapless`.

> The laptop and the load generator share the same CPU, and the laptop CPU differs from the OCI VM.
> Compare cores: `nproc` on the laptop vs on the server. Treat the numbers as **relative** (before/after a change), not as production numbers.

Stop the servers: `pkill -f "uvicorn main:app"; pkill -f "uvicorn platform_main:app"`.

---

## Part 2 — Live server (after the Oracle notice)

### 2a. Notify Oracle (5 business days before)

Send the email in `ORACLE_NOTICE_EMAIL.md` to **security_test_notification_grp@oracle.com**. Testing may start 5 business days later and may last at most 10 consecutive days. Load/stress testing stays forbidden.

### 2b. Configuration review on the server (no notice needed)

```bash
cd /srv/bayan-pos && sudo -u bayan git pull     # brings tools/sectest
sudo bash tools/sectest/server_checks.sh
```

### 2c. Prepare test tenants on production (in the console)

1. Console → new tenant `sec-a` (جمعية أهلية, licence number, VAT off), and again `sec-b`. Save both temporary passwords.
2. Log in to each on `https://sahlpos.roaa.sa`, set the password (the **same** password for every test user), complete the national address in Settings, and add two users: `cashier` (كاشير) and `locktest` (كاشير).
3. A separate console admin for the test (never use yours):
   `sudo -u bayan .venv/bin/python manage.py platform-admin create sectest "Security test"` → log in once on the console, scan the QR, **copy the manual key**.
4. `cp config.live.example.json config.live.json` and fill in the passwords and the manual key.

### 2d. Run (from the laptop)

```bash
cd ~/bayan-sectest/tools/sectest
bash external_checks.sh
~/.venvs/bayan-sectest/bin/python security_suite.py --config config.live.json
```

### 2e. Clean up afterwards

```bash
cd /srv/bayan-pos/backend
sudo -u bayan .venv/bin/python manage.py platform-admin disable sectest
sudo -u bayan .venv/bin/python manage.py delete sec-a --yes      # test invoices: manage.py may purge them
sudo -u bayan .venv/bin/python manage.py delete sec-b --yes
```

The console refuses to delete tenants with invoices (6-year retention); `manage.py delete` is the emergency route and is correct here because these invoices are test data. `locktest` stays locked for 15 minutes after the run — that is the lockout check working.
