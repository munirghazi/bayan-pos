# Release 1.1 — split payment, transfer proof, drafts, returns search, printing

**Migration:** `0027_payments_drafts` (after `0026_zatca_release1`)
**Base commit:** `64f4f12`

## What changes

| # | Change |
|---|---|
| 1 | **Default units for every tenant.** Tenants created with `manage.py` (such as `train`) had none. They're created automatically at start-up, and by `manage.py create` from now on. |
| 2 | **The whole menu fits a 1366×768 screen.** The user, password and logout controls share one row, the menu items are tighter on short screens, and the scrollbar is visible. |
| 3 | **Printing happens inside the same page** (hidden frame), so Chrome's full print dialog appears over the whole screen. This applies to the invoice, credit note and donation receipt. |
| 4 | **One document window** with print, PDF, WhatsApp and email for invoices, credit notes and receipts. The message texts carry **the tenant's own name**; "جمعية بيان" was hard-coded before. |
| 5 | **Split payment.** The payment window lets the cashier add cash, card and transfer tenders and shows what's left and the change. **Only cash can be more than what's left.** Card and transfer must not exceed it. |
| 6 | **Bank-transfer proof.** An image or PDF up to 5 MB, required before issuing (an option in Settings can switch the requirement off). It's stored privately, **not** in the public `uploads` folder, can be opened only from inside the system, and is used for one document only. |
| 7 | **Drafts.** A sale or donation whose proof isn't ready yet is saved as a draft: no number, no QR, no stock deduction, but the items are reserved. Attaching the proof issues the real document, which gets its number only then. Drafts are cancelled automatically at the end of the day. |
| 8 | **Refunds.** Cash is always allowed, plus any method used on the invoice. The refund method prints on the credit note. |
| 9 | **Register closing (Z-report).** Totals come from the payment lines, so split invoices count correctly, and **cash refunds are deducted from expected cash**. |
| 10 | **Returns screen: invoice search.** Search by number or part of it, transfer or card reference, customer name or mobile, date, amount, and payment method. Each result shows how much has already been returned. |
| 11 | **Reports.** Totals per method come from the payment lines. Each invoice shows its tenders, the change and a link to the transfer proof. |

**Existing data:**
- Each existing invoice gets one payment line with its method and total.
- Each existing credit note gets its refund method (the original invoice's method).
- Nothing is deleted.

---

## Part A — on your laptop

```bash
cd ~/"Development/POS for charity"
git checkout main && git pull
git checkout -b feat/release-1-1
unzip -o ~/Downloads/release-1-1.zip
git status
```

`git status` should show **11 new files** and **26 modified files**, including `.gitignore`.

```bash
git add -A .gitignore backend/*.py backend/routers backend/migrations backend/tests frontend/src APPLY_release_1_1.md RELEASE_1_1_CHECKLIST.md
git status            # nothing under backend/.venv
git commit -m "Release 1.1: split payment, transfer proof, drafts, invoice search, refunds, in-page printing, default units"
git push -u origin feat/release-1-1
git checkout main && git merge --ff-only feat/release-1-1 && git push
git log --oneline -2
```

---

## Part B — on the server

**1. Back up.** The folder already exists from Release 1.

```bash
sudo -u postgres pg_dump -Fc -d pos -f /var/backups/bayan-pos/pos-before-0027-$(date +%F-%H%M).dump
sudo ls -lh /var/backups/bayan-pos/
```

**2. Stop, pull, migrate.**

```bash
sudo systemctl stop bayan-pos
cd /srv/bayan-pos && sudo -u bayan git pull && sudo -u bayan git log --oneline -1
cd backend
sudo -u bayan bash -c 'set -a; . .env; APP_DB_ROLE=pos_app .venv/bin/alembic upgrade head'
sudo -u bayan bash -c 'set -a; . .env; .venv/bin/alembic current'
```

`alembic current` should show `0027_payments_drafts (head)`.

**3. Private folder for transfer proofs.** The app creates it automatically. Creating it now with the right permissions is safer:

```bash
sudo -u bayan mkdir -p /srv/bayan-pos/backend/storage/proofs
sudo chmod 750 /srv/bayan-pos/backend/storage
```

**4. Build and start.**

```bash
cd /srv/bayan-pos/frontend && sudo -u bayan npm ci && sudo -u bayan npm run build
sudo systemctl start bayan-pos
sleep 3; curl -s localhost:8000/health; echo
sudo -u postgres psql -d pos -c "SELECT count(*) AS payments, (SELECT count(*) FROM sales) AS sales FROM sale_payments;"
```

The two numbers must be equal: one payment line for each existing invoice.

> ⚠️ **Backups:** transfer proofs are **files** in `backend/storage/`. `pg_dump` doesn't include them. Until we set up automatic backups, copy the folder occasionally:
> `sudo tar czf /var/backups/bayan-pos/proofs-$(date +%F).tgz -C /srv/bayan-pos/backend storage`

---

## Rollback

**Restore from backup** (before any new sales):

```bash
sudo systemctl stop bayan-pos
cd /srv/bayan-pos && sudo -u bayan git checkout 64f4f12
sudo -u postgres pg_restore --clean --if-exists -d pos /var/backups/bayan-pos/pos-before-0027-<stamp>.dump
cd frontend && sudo -u bayan npm run build && sudo systemctl start bayan-pos
```

**Or downgrade the schema** (keeps sales; their payment lines and drafts are deleted):

```bash
cd /srv/bayan-pos/backend
sudo -u bayan bash -c 'set -a; . .env; APP_DB_ROLE=pos_app .venv/bin/alembic downgrade 0026_zatca_release1'
```

Then check out `64f4f12` and rebuild.

---

## Known limits

- **Prices in a draft:** a draft is priced at the product price **when it's issued**. If the price changes before the draft is issued, the total changes and the payment no longer matches, so the issue is refused. Cancel the draft and enter the sale again. Drafts last one day at most.
- **WhatsApp and email:**
  - WhatsApp opens with the text ready, and the PDF is downloaded to attach by hand.
  - Email is sent from the server only if SMTP is set in `.env`. Otherwise it opens the email program.

  Proper sending through providers comes in Release 3 (the messaging setup screen).
- **A refund to card or transfer** is only recorded on the credit note. The actual transfer back to the customer is done outside the system.
