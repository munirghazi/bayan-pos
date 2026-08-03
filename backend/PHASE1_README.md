# Phase 1 (backend) — Locations, Registers, Branch-scoped Sales

Adds branches and registers to the multi-tenant model. **Backend only** — the
admin screens and the POS register picker are Part B (frontend, next).

**Verified:** `pytest tests/` → 9 passed (isolation + kitting + locations), and
the `0002 → 0003` upgrade auto-provisions a default branch for existing tenants.

## What's new

- **Location (فرع)** and **Register (صندوق)** — tenant-scoped, RLS-isolated.
- **`users.location_id`** — a user's current branch (nullable). Null = all branches
  (admins). An admin can assign/reassign it at any time.
- **`sales.register_id`** — every sale can be tagged to the register it happened on.
- **Auto default branch** — every tenant gets "الفرع الرئيسي" + "الصندوق 1"
  automatically (migration provisions existing tenants; bootstrap and
  `manage.py create` provision new ones). Single-branch orgs need zero setup.
- **Branch guard on sales** — a branch-assigned user can only sell on a register in
  their own branch; admins (no branch) can sell on any register.

## Apply

```bash
cd backend
APP_DB_ROLE=pos_app alembic upgrade head    # runs 0003; provisions default branches
# restart uvicorn
pytest -q tests/
```

## API contract (for the frontend, Part B)

Locations (`/api/locations`):
- `GET  /api/locations/`            → list active branches
- `POST /api/locations/`           (admin) `{ "name": "..." }`
- `PUT  /api/locations/{id}`       (admin) `{ "name"?, "is_active"? }`
- `DELETE /api/locations/{id}`     (admin) → deactivates

Registers (`/api/registers`):
- `GET  /api/registers/?location_id=`  → list active registers (optionally by branch)
- `POST /api/registers/`           (admin) `{ "name": "...", "location_id": N }`
- `PUT  /api/registers/{id}`       (admin) `{ "name"?, "location_id"?, "is_active"? }`
- `DELETE /api/registers/{id}`     (admin) → deactivates

Users — create/update now accept **`location_id`** (nullable), and the user
response includes it.

Sales — `POST /api/sales/` now accepts **`register_id`** (optional). The response
includes `register_id`. A cashier posting a register outside their branch gets `403`.

## Frontend to build next (Part B)

1. **Branches & Registers admin screen** (manage locations + registers).
2. **Branch dropdown** in the user form (assign/reassign a user's branch).
3. **POS register picker** — cashier selects their register (remembered per browser);
   send `register_id` with each sale.
4. Wire the **sidebar** to show the logged-in tenant's real name (small `/auth/me`
   addition) — I'll fold this in with the settings work.
