# Release 1.1 — test checklist (training tenant)

Use a private window and press Ctrl+Shift+R after the deploy.

## 1. Units and menu
- [ ] The whole menu shows at 1366×768, from لوحة التحكم down to الخصوصية, with the logout and password icons at the bottom.
- [ ] **وحدات القياس** shows the default units (حبة، كرتون، كجم…).

## 2. Split payment (POS)
- [ ] Add an item at 115 and press **الدفع وإصدار الفاتورة**. The payment window opens.
- [ ] Cash 100 + **شبكة** 50 with a transaction code: it shows the change, **35.00**. Issue the invoice.
- [ ] The invoice lists both tenders and "الباقي للعميل 35.00".
- [ ] These are refused:
  - [ ] card or transfer more than what's left
  - [ ] cash less than the total
  - [ ] card with no transaction code

## 3. Printing
- [ ] Press **طباعة** in the invoice window. The print dialog opens **full-screen**, not inside a small window.
- [ ] It prints correctly on the Epson 80mm.

## 4. Transfer proof
- [ ] A transfer sale with no proof: the **إصدار الفاتورة** button is disabled.
- [ ] Attach an image or PDF of the transfer, then issue the invoice.
- [ ] The invoice window shows a **📎 إثبات التحويل** link that opens the file.

## 5. Draft
- [ ] A transfer sale with no proof: choose **حفظ كمسودة**. No invoice number is issued.
- [ ] The **المسودات (1)** button appears in the POS.
- [ ] Try selling more of the same item than is left unreserved. It's refused with "محجوز في مسودات".
- [ ] **المسودات → إرفاق الإثبات وإصدار**: the invoice is issued with the next number in sequence, with no gap.
- [ ] Cancel another draft. Its items are released.

## 6. Returns
- [ ] **المرتجعات** opens on a list of the last 30 days of invoices.
- [ ] Each of these filters works:
  - [ ] part of the invoice number
  - [ ] the customer's mobile
  - [ ] the card transaction code
  - [ ] the date
  - [ ] the payment method
- [ ] Open an invoice paid by card. The refund options are **شبكة** and **نقدي** only.
- [ ] The credit note shows the refund method, with print, PDF, WhatsApp and email.

## 7. Register closing
- [ ] **إغلاق الصندوق** shows cash, card and transfer from the payment lines, plus **مرتجعات نقدية**.
- [ ] Expected cash = cash − cash refunds.

## 8. Donations
- [ ] A transfer donation with no proof: only **حفظ كمسودة** is available. Issue it later from the POS drafts with the proof attached.
- [ ] The donations page shows 📎 next to a donation that has a proof.

## 9. The setting
- [ ] Settings → payment methods: turn off "إلزام إرفاق إثبات التحويل". A transfer can now be issued with no proof.
- [ ] Turn it back on.
