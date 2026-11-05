"""Release 1.1 — tenders on a document.

Rules (agreed):
* an invoice may be paid with several tenders (cash / card / transfer);
* only CASH may exceed what is left — the change comes out of cash; card and
  transfer must not exceed the amount still due;
* card needs the terminal transaction code (reconciliation);
* transfer needs an uploaded proof (unless the tenant switched that off, or the
  caller is saving a DRAFT that waits for the proof);
* a proof is used by exactly one document.
"""
from __future__ import annotations

from decimal import Decimal

from fastapi import HTTPException
from pydantic import BaseModel

import invoicing as inv

METHOD_AR = {"cash": "نقدي", "card": "شبكة", "transfer": "تحويل بنكي"}


class PaymentIn(BaseModel):
    method: str
    amount: float
    card_ref: str | None = None
    proof_id: int | None = None


def tenant_payment_settings(db) -> tuple[set[str], bool]:
    from database import TenantSettings
    st = db.query(TenantSettings).first()
    enabled = {m.strip() for m in ((st.payment_methods if st else None) or "cash,card,transfer").split(",")
               if m.strip()}
    require_proof = bool(getattr(st, "require_transfer_proof", True)) if st else True
    return enabled, require_proof


def check_proof(db, proof_id: int):
    from database import PaymentProof
    proof = db.query(PaymentProof).filter(PaymentProof.id == proof_id).first()
    if not proof:
        raise HTTPException(status_code=400, detail="إثبات التحويل غير موجود")
    if proof.used:
        raise HTTPException(status_code=400, detail="إثبات التحويل مستخدم في مستند آخر")
    return proof


def mark_proof_used(db, proof_id: int | None, ref: str) -> None:
    if not proof_id:
        return
    from database import PaymentProof
    p = db.query(PaymentProof).filter(PaymentProof.id == proof_id).first()
    p.used = True
    p.used_ref = ref[:40]


def validate_payments(db, payments: list[PaymentIn], total: Decimal, allowed: set[str],
                      draft: bool = False) -> tuple[list[dict], Decimal, bool]:
    """Returns (lines, change, missing_proof).

    lines: [{method, amount (applied), tendered, card_ref, proof_id}]
    """
    if not payments:
        raise HTTPException(status_code=400, detail="أضف طريقة دفع واحدة على الأقل")
    enabled, require_proof = tenant_payment_settings(db)
    total = inv.q2(total)

    cash_tendered = Decimal(0)
    others, missing_proof, seen_proofs = [], False, set()
    for p in payments:
        m = (p.method or "").strip()
        if m not in allowed:
            raise HTTPException(status_code=400, detail="طريقة الدفع غير مسموحة لهذه العملية")
        if m not in enabled:
            raise HTTPException(status_code=400, detail=f"طريقة الدفع «{METHOD_AR.get(m, m)}» غير مفعّلة في الإعدادات")
        amt = inv.q2(p.amount)
        if amt <= 0:
            raise HTTPException(status_code=400, detail="مبلغ الدفع يجب أن يكون أكبر من صفر")
        if m == "cash":
            cash_tendered += amt
            continue
        ref = (p.card_ref or "").strip() or None
        if m == "card" and not ref:
            raise HTTPException(status_code=400, detail="الرجاء إدخال رمز العملية للدفع بالشبكة")
        if m == "transfer":
            if p.proof_id:
                if p.proof_id in seen_proofs:
                    raise HTTPException(status_code=400, detail="لا يمكن استخدام نفس الإثبات مرتين")
                seen_proofs.add(p.proof_id)
                check_proof(db, p.proof_id)
            elif require_proof:
                if not draft:
                    raise HTTPException(status_code=400,
                                        detail="أرفق إثبات التحويل البنكي أو احفظ العملية كمسودة")
                missing_proof = True
        others.append({"method": m, "amount": amt, "tendered": None, "card_ref": ref,
                       "proof_id": p.proof_id if m == "transfer" else None})

    non_cash = sum((o["amount"] for o in others), Decimal(0))
    if non_cash > total:
        raise HTTPException(status_code=400,
                            detail="مبلغ الشبكة / التحويل أكبر من المتبقي — الزيادة مسموحة في النقد فقط")
    paid = non_cash + cash_tendered
    if paid < total:
        raise HTTPException(status_code=400,
                            detail=f"المبلغ المدفوع ({paid:.2f}) أقل من الإجمالي ({total:.2f})")
    change = inv.q2(paid - total)
    lines = list(others)
    if cash_tendered > 0:
        applied = inv.q2(cash_tendered - change)
        if applied <= 0:
            raise HTTPException(status_code=400,
                                detail="لا حاجة لدفع نقدي — المبلغ مغطى بطرق الدفع الأخرى")
        lines.insert(0, {"method": "cash", "amount": applied, "tendered": cash_tendered,
                         "card_ref": None, "proof_id": None})
    return lines, change, missing_proof


def summary_method(lines: list[dict]) -> str:
    methods = {l["method"] for l in lines}
    return methods.pop() if len(methods) == 1 else "mixed"


def payment_dict(p) -> dict:
    return {"method": p.method, "amount": inv.money(p.amount),
            "tendered": inv.money(p.tendered) if p.tendered is not None else None,
            "card_ref": p.card_ref, "proof_id": p.proof_id}
