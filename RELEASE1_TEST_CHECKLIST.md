# Release 1 — test checklist (training tenant)

Run these on the training tenant in a private window after deploying. Tick each one.

## 1. Branch codes
- [ ] **Branches & Registers:** each branch shows a code badge (`B01` …).
- [ ] On a branch that has never issued anything, click the badge and change the code. It saves.
- [ ] After one sale on that branch, the badge is greyed out and the code can't be changed.

## 2. Invoice
- [ ] **POS:** sell a product priced 115.00 (cash). The toast shows `B01-INV-00000X`.
- [ ] The invoice shows:
  - [ ] the title **فاتورة ضريبية مبسطة**
  - [ ] the number
  - [ ] the date and time **in Riyadh time**
  - [ ] *الإجمالي غير شامل الضريبة 100.00*, *ضريبة القيمة المضافة (15%) 15.00*, total 115.00
  - [ ] the VAT number and a QR
- [ ] Scan the QR with the **ZATCA app** (or any ZATCA QR reader). It shows:
  - [ ] seller name and VAT number
  - [ ] time
  - [ ] total 115.00 and VAT 15.00
- [ ] A second sale gets the next number, with no gap.
- [ ] A card sale with no transaction reference is refused.
- [ ] A product marked tax-exempt shows *(معفى)* and adds no VAT.

## 3. Reprint doesn't change
- [ ] **Settings:** change the VAT rate to 5 and save.
- [ ] **Reports → المبيعات:** reprint the invoice from step 2. It still shows 15% / 15.00.
- [ ] Set the VAT rate back to **15**.

## 4. Credit note
- [ ] **Returns:** type the invoice number. Typing just the digits also works.
- [ ] Enter a return quantity and leave the reason empty. The button stays disabled.
- [ ] Enter a reason and issue. The credit note opens with:
  - [ ] **إشعار دائن لفاتورة ضريبية مبسطة**
  - [ ] a `B01-CN-…` number
  - [ ] the original invoice number and date
  - [ ] the reason, the VAT reversed, and a QR
- [ ] It can be printed again from **آخر الإشعارات الدائنة**.
- [ ] **Reports → المبيعات** shows the credit note, net sales and net VAT.

## 5. Donations
- [ ] **POS:** add an item to the cart. The **تبرع** button is disabled.
- [ ] Empty the cart and open **تبرع**. Only **شبكة** and **تحويل** are offered, with no cash.
- [ ] Choose card with no reference. It is refused.
- [ ] A transfer donation prints **إيصال تبرع** with:
  - [ ] a `B01-DON-…` number
  - [ ] no VAT number and no QR
  - [ ] the line *هذا الإيصال ليس فاتورة ضريبية*
- [ ] **Donations page:** there is no delete button.
  - [ ] An admin sees a void button. It asks for a reason.
  - [ ] The row shows **ملغى** and leaves the total.
  - [ ] The reprint shows **ملغى** with the reason.
- [ ] A cashier user does **not** see the void button.

## 6. Donations flag off
- [ ] Turn the tenant's donations off. On the server:
  ```bash
  sudo -u postgres psql -d pos -c "UPDATE tenants SET donations_enabled=false WHERE slug='<training-slug>'"
  ```
- [ ] Log out and back in, then check:
  - [ ] no **التبرعات** in the sidebar
  - [ ] no donate button in the POS
  - [ ] no donations tab in Reports
  - [ ] no donation cards or list on the dashboard
  - [ ] typing `/donations` in the address bar goes back to the dashboard
- [ ] Turn it back on with `=true` and log in again. Everything comes back.

## 7. Cannot be edited
Run this on the server. It must **fail** with "issued document … cannot be update":
```bash
sudo -u postgres psql -d pos -c "UPDATE sales SET total = 1 WHERE id = (SELECT max(id) FROM sales)"
```

## 8. Not VAT-registered (optional)
- [ ] Set `vat_enabled=false` on the training tenant, the same way as step 6.
- [ ] A new sale prints **فاتورة**, with no VAT lines and no QR.
- [ ] Set it back to `true`.
