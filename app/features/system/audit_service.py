from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy.orm import Session

from app.features.system.system_repository import audit_repository
from app.features.system.system_schemas import AuditLogCreate


def _serialize_value(val: Any) -> Any:
    if isinstance(val, (datetime, date, time)):
        return val.isoformat()
    if isinstance(val, Enum):
        return val.value
    if isinstance(val, Decimal):
        return float(val)
    if isinstance(val, (bytes, bytearray)):
        return "<binary>"
    return val


def _serialize_dict(data: dict) -> dict[str, Any]:
    return {
        k: _serialize_value(v)
        for k, v in data.items()
        if k != "password_hash"
    }


def _serialize_sqlalchemy_model(model: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for column in model.__table__.columns:
        if column.name == "password_hash":
            continue
        val = getattr(model, column.name, None)
        result[column.name] = _serialize_value(val)
    return result


def _serialize_regular_model(model: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in model.__dict__.items():
        if not key.startswith("_") and key != "password_hash":
            val = _serialize_value(value)
            if val is not value or isinstance(value, (str, int, float, bool)) or value is None:
                result[key] = val
    return result


def serialize_model(model: Any) -> dict[str, Any]:
    if model is None:
        return {}
    if isinstance(model, dict):
        return _serialize_dict(model)
    if hasattr(model, "__table__"):
        return _serialize_sqlalchemy_model(model)
    if hasattr(model, "__dict__"):
        return _serialize_regular_model(model)
    return {}


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

    def _prepare_raw_data(self, model: Any | None, data: dict | None) -> dict | None:
        raw = serialize_model(model) if model is not None else {}
        if data:
            if not raw:
                raw = data.copy()
            else:
                raw.update(data)
        return raw or None

    def _resolve_entity_info(
            self, entity: str | None, entity_id: int | None, old_model: Any | None, new_model: Any | None
    ) -> tuple[str, int]:
        resolved_entity = entity
        if resolved_entity is None:
            if new_model is not None and hasattr(new_model, "__tablename__"):
                resolved_entity = new_model.__tablename__.upper()
            elif old_model is not None and hasattr(old_model, "__tablename__"):
                resolved_entity = old_model.__tablename__.upper()
            else:
                resolved_entity = "SYSTEM"

        resolved_id = entity_id
        if resolved_id is None:
            if new_model is not None and hasattr(new_model, "id"):
                resolved_id = getattr(new_model, "id", 0)
            elif old_model is not None and hasattr(old_model, "id"):
                resolved_id = getattr(old_model, "id", 0)
            else:
                resolved_id = 0

        return resolved_entity, resolved_id

    def _compute_final_data(self, raw_old: dict | None, raw_new: dict | None) -> tuple[dict | None, dict | None]:
        if raw_old is not None and raw_new is not None:
            return self.compute_diffs(raw_old, raw_new)
        return raw_old, raw_new

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
        raw_old = self._prepare_raw_data(old_model, old_data)
        raw_new = self._prepare_raw_data(new_model, new_data)
        resolved_entity, resolved_id = self._resolve_entity_info(entity, entity_id, old_model, new_model)
        final_old, final_new = self._compute_final_data(raw_old, raw_new)

        return self.log(
            db,
            user_id=user_id,
            action=action,
            entity=resolved_entity,
            entity_id=resolved_id,
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

    async def async_log(
            self,
            db,
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
        return await audit_repository.async_create(db, obj_in=obj_in)

    async def async_log_change(
            self,
            db,
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
        raw_old = self._prepare_raw_data(old_model, old_data)
        raw_new = self._prepare_raw_data(new_model, new_data)
        resolved_entity, resolved_id = self._resolve_entity_info(entity, entity_id, old_model, new_model)
        final_old, final_new = self._compute_final_data(raw_old, raw_new)

        return await self.async_log(
            db,
            user_id=user_id,
            action=action,
            entity=resolved_entity,
            entity_id=resolved_id,
            old_data=final_old,
            new_data=final_new,
        )


audit_service = AuditService()
