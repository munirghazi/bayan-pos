"""Idempotency for POST endpoints: an Idempotency-Key header makes a repeated
request return the original result instead of creating a duplicate."""
import json
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi.encoders import jsonable_encoder


def replay(db: Session, key: str | None, endpoint: str):
    if not key:
        return None
    row = db.execute(text(
        "SELECT response_json FROM idempotency_keys WHERE idem_key=:k AND endpoint=:e"),
        {"k": key, "e": endpoint}).first()
    return json.loads(row[0]) if row else None


def store(db: Session, key: str | None, endpoint: str, response_obj) -> None:
    if not key:
        return
    payload = json.dumps(jsonable_encoder(response_obj), ensure_ascii=False)
    # tenant_id is filled by the column default from the session GUC
    db.execute(text(
        "INSERT INTO idempotency_keys (idem_key, endpoint, response_json) "
        "VALUES (:k, :e, :p) ON CONFLICT (tenant_id, idem_key, endpoint) DO NOTHING"),
        {"k": key, "e": endpoint, "p": payload})
    db.commit()
