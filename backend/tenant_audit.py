"""Tenant-side audit trail for sensitive actions."""
from sqlalchemy import text
from sqlalchemy.orm import Session


def tenant_audit(db: Session, user, action: str, target=None, detail=None) -> None:
    db.execute(text(
        "INSERT INTO tenant_audit_log (user_id, username, action, target, detail) "
        "VALUES (:uid, :un, :a, :t, :d)"),
        {"uid": getattr(user, "id", None), "un": getattr(user, "username", None),
         "a": action, "t": (str(target) if target is not None else None), "d": detail})
    db.commit()
