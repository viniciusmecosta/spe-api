from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from app.features.system.system_repository import audit_repository
from app.features.system.system_schemas import AuditLogCreate


def serialize_model(model: Any) -> dict[str, Any]:
    if model is None:
        return {}
    if isinstance(model, dict):
        return {
            k: (
                v.isoformat()
                if isinstance(v, (datetime, date, time))
                else v.value
                if isinstance(v, Enum)
                else float(v)
                if isinstance(v, Decimal)
                else v
            )
            for k, v in model.items()
            if k != "password_hash"
        }

    result: dict[str, Any] = {}
    if hasattr(model, "__table__"):
        for column in model.__table__.columns:
            if column.name == "password_hash":
                continue
            val = getattr(model, column.name, None)
            if isinstance(val, (datetime, date, time)):
                result[column.name] = val.isoformat()
            elif isinstance(val, Enum):
                result[column.name] = val.value
            elif isinstance(val, Decimal):
                result[column.name] = float(val)
            elif isinstance(val, (bytes, bytearray)):
                result[column.name] = "<binary>"
            else:
                result[column.name] = val
    elif hasattr(model, "__dict__"):
        for key, value in model.__dict__.items():
            if not key.startswith("_") and key != "password_hash":
                if isinstance(value, (datetime, date, time)):
                    result[key] = value.isoformat()
                elif isinstance(value, Enum):
                    result[key] = value.value
                elif isinstance(value, Decimal):
                    result[key] = float(value)
                elif isinstance(value, (bytes, bytearray)):
                    result[key] = "<binary>"
                elif isinstance(value, (str, int, float, bool)) or value is None:
                    result[key] = value
    return result


class AuditService:
    def log(
            self,
            db: Session,
            user_id: int | None,
            action: str,
            *,
            entity: str,
            entity_id: int,
            old_data: dict | None = None,
            new_data: dict | None = None,
    ):
        obj_in = AuditLogCreate(
            user_id=user_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            old_data=old_data,
            new_data=new_data
        )
        return audit_repository.create(db, obj_in)

    def log_change(
        self,
        db: Session,
        user_id: int | None,
        action: str,
        *,
        entity: str | None = None,
        entity_id: int | None = None,
        old_model: Any | None = None,
        new_model: Any | None = None,
        old_data: dict | None = None,
        new_data: dict | None = None,
    ):
        raw_old = serialize_model(old_model) if old_model is not None else {}
        if old_data:
            if not raw_old:
                raw_old = old_data.copy()
            else:
                raw_old.update(old_data)
        raw_old = raw_old or None

        raw_new = serialize_model(new_model) if new_model is not None else {}
        if new_data:
            if not raw_new:
                raw_new = new_data.copy()
            else:
                raw_new.update(new_data)
        raw_new = raw_new or None

        if entity is None:
            if new_model is not None and hasattr(new_model, "__tablename__"):
                entity = new_model.__tablename__.upper()
            elif old_model is not None and hasattr(old_model, "__tablename__"):
                entity = old_model.__tablename__.upper()
            else:
                entity = "SYSTEM"

        if entity_id is None:
            if new_model is not None and hasattr(new_model, "id"):
                entity_id = getattr(new_model, "id", 0)
            elif old_model is not None and hasattr(old_model, "id"):
                entity_id = getattr(old_model, "id", 0)
            else:
                entity_id = 0

        final_old = None
        final_new = None

        if raw_old is not None and raw_new is not None:
            final_old, final_new = self.compute_diffs(raw_old, raw_new)
        elif raw_old is not None:
            final_old = raw_old
        elif raw_new is not None:
            final_new = raw_new

        return self.log(
            db,
            user_id=user_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            old_data=final_old,
            new_data=final_new,
        )

    def compute_diffs(self, old_data: dict, new_data: dict) -> tuple[dict, dict]:
        actual_old = {}
        actual_new = {}

        all_keys = set(old_data.keys()).union(new_data.keys())
        for key in all_keys:
            old_val = old_data.get(key)
            new_val = new_data.get(key)
            if old_val != new_val:
                if key in old_data:
                    actual_old[key] = old_val
                if key in new_data:
                    actual_new[key] = new_val

        return actual_old, actual_new

    def get_logs(self, db: Session, action: str | None = None,
                 start_date: date | None = None, end_date: date | None = None,
                 order_by: str = "desc", skip: int = 0, limit: int = 100):
        return audit_repository.get_logs(
            db, action=action, start_date=start_date, end_date=end_date,
            order_by=order_by, skip=skip, limit=limit
        )


audit_service = AuditService()
