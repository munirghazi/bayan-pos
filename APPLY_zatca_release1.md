# Release 1 — ZATCA Phase 1 compliance + donation rules

**Migration:** `0026_zatca_release1` (after `0025_product_is_consignment`)
**Base commit:** `0f8f25c` (forced password change)

---

## What changes

### Invoices (B2C, simplified tax invoice)
- **Separate numbering per tenant and branch, with no gaps:** `B01-INV-000001`, `B01-CN-000001`, `B01-DON-000001`. Each counter row is locked while a document is issued, so two cashiers can never get the same number. If an issue fails, its number is rolled back.
- **Every branch has a code** (`B01`, `B02` …). It is assigned automatically and can be changed on **Branches & Registers** only until the branch issues its first document. After that it is locked.
- **Each invoice is stored exactly as it was issued:**
  - per line: VAT rate, VAT amount, total, product name and unit
  - per invoice: totals, the seller's name, VAT number and address, and the ZATCA QR
  - Reprints read these stored values, so changing settings later never changes an old invoice.
- **Money is stored as `numeric`** (no floating-point rounding drift).
- **Title and QR depend on VAT registration:**
  - "فاتورة ضريبية مبسطة" + QR only when the tenant is VAT-registered (`vat_enabled` and a VAT number).
  - Otherwise a plain "فاتورة", with no VAT and no QR.
- **The VAT number is validated** (15 digits, starting and ending with 3) before any tax invoice is issued.
- **Times are stored in UTC and always shown in Riyadh time**, whatever the device clock is set to. Report days are Riyadh calendar days.
- **Card sales require the transaction reference** on the server too.
- **Phase 2 groundwork:** each invoice and credit note carries a UUID, a counter and a hash linked to the previous document in the branch.

### Credit notes (returns)
- A credit note is a **printable document**: "إشعار دائن لفاتورة ضريبية مبسطة".
- It shows the original invoice number and date, and a **reason, which is now required**.
- It uses the original invoice's branch series and **reverses VAT at the original rate**.
- Returns are looked up by invoice number. Typing just `123` means `<your branch>-INV-000123`.

### Cannot be changed after issue (enforced in the database)
- Sales, sale lines, credit notes and their lines can't be updated or deleted.
- Donations can't be deleted. An admin can **void** one with a reason; the receipt keeps its number and shows "ملغى".
- The only edits allowed on a donation are clearing the donor's name and note (PDPL) and the one-way void.
- `manage.py delete <slug> --yes` still purges a whole tenant on purpose.

### Donations — your 4 points
1. **No cash.** Card (POS terminal) or bank transfer only, and only methods enabled in settings. This is enforced on the server and in both the POS and Donations screens. Card needs the transaction reference.
2. **No mixing.** The Donate button is disabled while the cart has items. The two APIs are separate (there are no donation fields on a sale).
3. **Receipt, not invoice.** "إيصال تبرع" with its own `B01-DON-` number, **no VAT number, no QR**, and the line "هذا الإيصال ليس فاتورة ضريبية".
4. **Flag off hides everything:**
   - Sidebar link, POS button, `/donations` (even typed as a URL), the Reports tab, and the dashboard cards and list are all hidden.
   - The API returns 403 for donations list, detail, report and void.

### Reports
- **Sales report adds:** VAT total, credit notes (count, amount, VAT), net sales, net VAT. The CSV includes all of these.
- **Donations report:** voided receipts are listed but excluded from totals.

### Clean-up
- Removed the stray copies `backend/backend/` and `backend/frontend/`. They broke the test run.

### Existing data
The migration back-fills everything already in the database:
- Documents are numbered per branch in date order.
- VAT is computed from the tenant's current rate.
- Tenants without a branch get "الفرع الرئيسي" + "الصندوق 1".

Nothing is deleted.

---

## Part A — on your laptop

```bash
cd ~/"Development/POS for charity"
git checkout main && git pull
git checkout -b feat/zatca-release1
unzip -o ~/Downloads/zatca-release1.zip
git rm -r -q backend/backend backend/frontend
git status
```

`git status` should show:
- **6 new files:**
  - `backend/invoicing.py`
  - `backend/migrations/versions/0026_zatca_release1.py`
  - `backend/tests/test_zatca_release1.py`
  - `frontend/src/utils/datetime.js`
  - `APPLY_zatca_release1.md`
  - `RELEASE1_TEST_CHECKLIST.md`
- **24 modified files**
- the deleted stray folders

```bash
git add -A backend/*.py backend/routers backend/migrations backend/tests frontend/src APPLY_zatca_release1.md RELEASE1_TEST_CHECKLIST.md
git status   # make sure nothing under backend/.venv is staged
git commit -m "ZATCA release 1: per-branch numbering, invoice snapshot, credit notes, donation receipts, immutability"
git push -u origin feat/zatca-release1
git checkout main
git merge --ff-only feat/zatca-release1
git push
```

> ⚠️ Don't use `git add -A .` on its own. See "Repository warning" at the end.

---

## Part B — on the server

```bash
ssh -i ~/.ssh/<your-key> ubuntu@158.101.250.177
```

**1. Back up the database first.** Use the database name from `DATABASE_URL` in `/srv/bayan-pos/backend/.env`; it is normally `pos`.

```bash
sudo mkdir -p /var/backups/bayan-pos
sudo -u postgres pg_dump -Fc -d pos -f /var/backups/bayan-pos/pos-before-0026-$(date +%F-%H%M).dump
ls -lh /var/backups/bayan-pos/
```

**2. Stop the app** so no sale happens mid-migration.

```bash
sudo systemctl stop bayan-pos
```

**3. Pull, migrate, build, start.**

```bash
cd /srv/bayan-pos
sudo -u bayan git pull
sudo -u bayan git log --oneline -1
cd backend
sudo -u bayan bash -c 'set -a; . .env; APP_DB_ROLE=pos_app .venv/bin/alembic upgrade head'
sudo -u bayan bash -c 'set -a; . .env; .venv/bin/alembic current'
cd ../frontend && sudo -u bayan npm ci && sudo -u bayan npm run build
sudo systemctl start bayan-pos
sleep 3; curl -s localhost:8000/health; echo
```

- The `git log` line should show the new commit.
- `alembic current` should print `0026_zatca_release1 (head)`.

**4. Check the back-fill.**

```bash
sudo -u postgres psql -d pos -c "SELECT t.slug, l.code, s.invoice_number, s.total, s.vat_amount
  FROM sales s JOIN tenants t ON t.id=s.tenant_id JOIN locations l ON l.id=s.location_id
  ORDER BY t.slug, s.invoice_number LIMIT 20;"
sudo -u postgres psql -d pos -c "SELECT tenant_id, location_id, doc_type, last_value FROM document_sequences ORDER BY 1,2,3;"
```

There are no new Python or npm packages. `zoneinfo` is part of Python and uses the system time-zone data that Ubuntu already has.

---

## Part C — test on the training tenant

Use a private window and hard-refresh with Ctrl+Shift+R. The full checklist is in **RELEASE1_TEST_CHECKLIST.md**.

---

## Rollback

**Option 1 — restore the backup.** This is the cleanest, if done soon after the deploy. Any sales made after the deploy are lost.

```bash
sudo systemctl stop bayan-pos
cd /srv/bayan-pos && sudo -u bayan git checkout 0f8f25c
sudo -u postgres pg_restore --clean --if-exists -d pos /var/backups/bayan-pos/pos-before-0026-<stamp>.dump
cd frontend && sudo -u bayan npm run build && sudo systemctl start bayan-pos
```

**Option 2 — downgrade the schema.** This keeps sales made after the deploy, but they lose their new numbers. **Run the downgrade before checking out the old code**, because the old code doesn't contain the migration file.

```bash
sudo systemctl stop bayan-pos
cd /srv/bayan-pos/backend
sudo -u bayan bash -c 'set -a; . .env; APP_DB_ROLE=pos_app .venv/bin/alembic downgrade 0025_product_is_consignment'
cd .. && sudo -u bayan git checkout 0f8f25c
cd frontend && sudo -u bayan npm run build && sudo systemctl start bayan-pos
```

Afterwards, put the server back on `main` with `sudo -u bayan git checkout main` once you're ready to deploy again.

---

## Known limits (deliberately not in this release)

- **B2B (standard) tax invoices** — B2C only, as agreed. `sales.invoice_type` is already there (`simplified`).
- **ZATCA Phase 2:**
  - not yet done: XML (UBL 2.1), signing, CSID onboarding, reporting to Fatoora
  - The current hash is an internal tamper-evidence chain. Phase 2 starts its own chain per EGS unit at onboarding.
- **Donation receipts show the charity's *current* name and address.** Unlike invoices, they are not snapshotted.
- **The register closing (Z-report)** still counts sales only. Cash refunds from credit notes aren't deducted from expected cash yet.
- **The consignment VAT treatment** still needs your accountant's confirmation. Consigned lines are taxed like normal lines unless the product is marked exempt.

## ⚠️ Repository warning (found while building this)

`backend/.venv/` (about 2,400 files, a Python virtualenv) is committed to the GitHub repo. That's because `.gitignore` lists `venv/` but not `.venv/`. The repo is also public.

**Don't remove it in a hurry.** If it is deleted from git, the next `git pull` on the server would delete the server's own `.venv` and the app would stop.

This needs a planned clean-up:
1. Add `.venv/` to `.gitignore`.
2. Run `git rm -r --cached backend/.venv`.
3. On the server, rebuild the venv before restarting.

Do it as its own small release.
