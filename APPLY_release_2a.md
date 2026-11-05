# Release 2a — organization identity + national address

**Migration:** `0028_entity_identity` (after `0027_payments_drafts`)

## What changes

**Organization type** (stored separately from how the tenant operates)

| Group | Types | Registration number |
|---|---|---|
| Non-profit | جمعية أهلية · مؤسسة أهلية · وقف · جمعية تعاونية | رقم الترخيص |
| Commercial | شركة · مؤسسة فردية · متجر إلكتروني | رقم السجل التجاري |
| Commercial | عمل حر | رقم وثيقة العمل الحر |
| | أخرى | — |

**الرقم الموحد** (10 digits starting with 7) applies to every type and is checked in the database.

**Identity is platform-controlled.** The legal name (Arabic and English), the type, the registration numbers, the VAT number, VAT registration and the VAT rate:
- appear **read-only** in the tenant's Settings
- are changed only by the platform, using `manage.py identity` until the platform console arrives in 2b
- if the tenant tries to change them through the API, it gets a 403

**Donations are for non-profit types only.** Setting the type to a commercial one switches donations off. Even if the donations switch is turned back on, a commercial organization still can't receive donations: the API refuses (403) and the screens hide everything related to donations.

**The national address follows the address proof:**
- **Order:** short address → building number / street → secondary number / district → postal code → city → country.
- **Layout:** Arabic on the right, English on the left.
- **"الرقم الإضافي" is renamed "الرقم الفرعي"** (the data is kept).
- **Checks:**
  - short address: 4 letters + 4 digits
  - building number: 4 digits
  - secondary number: 4 digits
  - postal code: 5 digits
- **A warning, not a block,** if the digits of the short address don't match the building number.
- **Proof number and expiry date:** a reminder appears in Settings 30 days before the expiry.
- **"المنطقة"** is optional and no longer printed.
- **The option "إظهار العنوان بالإنجليزية في الفاتورة"** also prints the English name.

**On the invoice and receipt:**
- the national address in the proof's order, plus the short address
- **the unified number + the registration number that fits the type**
- **the closing line:** "جزاكم الله خيراً" for non-profits and "شكراً لتسوقكم معنا" for commercial types, changeable in Settings

All of this is stored on each document at the moment it's issued.

**Wording:** "الجمعية" is changed to "المنشأة" everywhere.

**Existing data:**
- `train` and `roaa` become **جمعية أهلية**.
- **The name and VAT number the tenant entered in Settings become the official record** (in `tenants`).
- The country becomes "المملكة العربية السعودية / Kingdom of Saudi Arabia".

---

## Part A — on your laptop

```bash
cd ~/"Development/POS for charity"
git checkout main && git pull
git checkout -b feat/release-2a
unzip -o ~/Downloads/release-2a.zip
git status        # 5 new files (incl. APPLY_release_2a.md) + 8 modified
git add -A backend/*.py backend/routers backend/migrations backend/tests frontend/src APPLY_release_2a.md
git commit -m "Release 2a: organization type and registration numbers (platform-controlled), national address in proof order AR/EN, donations for non-profits only"
git push -u origin feat/release-2a
git checkout main && git merge --ff-only feat/release-2a && git push
```

## Part B — on the server

```bash
sudo -u postgres pg_dump -Fc -d pos -f /var/backups/bayan-pos/pos-before-0028-$(date +%F-%H%M).dump
sudo systemctl stop bayan-pos
cd /srv/bayan-pos && sudo -u bayan git pull && sudo -u bayan git log --oneline -1
cd backend
sudo -u bayan bash -c 'set -a; . .env; APP_DB_ROLE=pos_app .venv/bin/alembic upgrade head'
sudo -u bayan bash -c 'set -a; . .env; .venv/bin/alembic current'      # 0028_entity_identity (head)
cd ../frontend && sudo -u bayan npm run build
sudo systemctl start bayan-pos
sleep 3; curl -s localhost:8000/health; echo
```

There are no new npm packages this time, so `npm ci` isn't needed.

## Part C — enter each tenant's identity (from the server)

To view a tenant's identity:

```bash
cd /srv/bayan-pos/backend
sudo -u bayan bash -c 'set -a; . .env; .venv/bin/python manage.py identity train'
```

To set it (put the real values in place of the examples):

```bash
sudo -u bayan bash -c 'set -a; . .env; .venv/bin/python manage.py identity roaa \
  --type nonprofit_association --name "..." --name-en "..." \
  --unified 7XXXXXXXXX --license XXXX --vat 3XXXXXXXXXXXXX3 --vat-enabled yes'
```

**Other cases:**
- **A commercial tenant:** `--type company --cr XXXXXXXXXX`. Donations switch off automatically.
- **A tenant that isn't VAT-registered:** `--vat-enabled no`. Its invoices become a plain "فاتورة" with no QR.

The command checks the formats and won't save anything wrong. If the registration number for the type is missing, it prints "! missing".

**Then, from the tenant's account:** **الإعدادات → بيانات المنشأة → العنوان الوطني**. Enter the address exactly as it appears on the address proof, with the expiry date.

## Rollback

```bash
sudo systemctl stop bayan-pos
cd /srv/bayan-pos/backend
sudo -u bayan bash -c 'set -a; . .env; APP_DB_ROLE=pos_app .venv/bin/alembic downgrade 0027_payments_drafts'
cd .. && sudo -u bayan git checkout <previous commit> && cd frontend && sudo -u bayan npm run build
sudo systemctl start bayan-pos
```

Or restore the dump taken in Part B.

## Test checklist (training tenant)

- [ ] **Settings → بيانات المنشأة**
  - [ ] The identity card shows "تُعدَّل من إدارة المنصة", and its fields can't be edited.
  - [ ] Type: جمعية أهلية.
- [ ] **National address**
  - [ ] The field order matches the proof, Arabic on the right and English on the left.
  - [ ] Save it.
  - [ ] Enter a short address that doesn't match the building number: a warning appears.
  - [ ] Set an expiry date less than 30 days away: the reminder appears.
- [ ] **New invoice**
  - [ ] The address is printed in the proof's order.
  - [ ] The short address is printed.
  - [ ] The unified number and licence number are printed.
  - [ ] The closing line is "جزاكم الله خيراً".
- [ ] **English option:** turn on "إظهار العنوان بالإنجليزية". The next invoice shows the English name and address.
- [ ] **Commercial type:** `manage.py identity train --type company`, then log out and back in. Donations disappear from the menu, the POS and the reports, and the closing line becomes "شكراً لتسوقكم معنا".
- [ ] **Return train to non-profit:**
  - [ ] Run `--type nonprofit_association`, then switch donations back on with:
    `sudo -u postgres psql -d pos -c "UPDATE tenants SET donations_enabled=true WHERE slug='train'"`
  - [ ] Log in again. Donations come back.
