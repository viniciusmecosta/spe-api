from datetime import datetime, timedelta
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.time_records.time_record_models import TimeRecord, get_local_time
from app.shared.enums import AdjustmentType
from app.shared.timezone import to_app_timezone


class AdjustmentAction(Protocol):
    async def apply(self, db: AsyncSession, adjustment: AdjustmentRequest, manager_id: int) -> None: ...
    async def revert(self, db: AsyncSession, adjustment: AdjustmentRequest, manager_id: int) -> None: ...


class NoPunchAction(AdjustmentAction):
    async def apply(self, db, adjustment, manager_id):
        return None

    async def revert(self, db, adjustment, manager_id):
        return None


async def _latest_version(db, record_id):
    versions = select(TimeRecord.id).where(TimeRecord.id == record_id).cte('adjustment_record_versions', recursive=True)
    versions = versions.union_all(select(TimeRecord.id).where(TimeRecord.original_record_id == versions.c.id))
    return (await db.scalars(select(TimeRecord).where(TimeRecord.id.in_(select(versions.c.id)))
                             .order_by(TimeRecord.id.desc()).limit(1))).first()


async def _matching_record(db, adjustment, ignored, created=False):
    if adjustment.applied_time_record_id is not None:
        return await _latest_version(db, adjustment.applied_time_record_id)
    target = to_app_timezone(datetime.combine(adjustment.target_date, adjustment.time))
    start = target.replace(second=0, microsecond=0)
    statement = select(TimeRecord).where(
        TimeRecord.user_id == adjustment.user_id, TimeRecord.record_type == adjustment.record_type,
        TimeRecord.record_datetime >= start, TimeRecord.record_datetime < start + timedelta(minutes=1),
        TimeRecord.is_ignored.is_(ignored),
    )
    if created:
        statement = statement.where(TimeRecord.ip_address == 'ADJUSTMENT_APPROVED')
    return (await db.scalars(statement.order_by(TimeRecord.id.desc()))).first()


def _ignore(record, manager_id):
    record.is_ignored = True
    record.deleted_at = get_local_time()
    record.deleted_by = manager_id


def _restore(record):
    record.is_ignored = False
    record.deleted_at = None
    record.deleted_by = None


class AddPunchAction(AdjustmentAction):
    async def apply(self, db, adjustment, manager_id):
        if adjustment.time is None:
            return
        record = None
        if adjustment.id is not None:
            record = await db.scalar(select(TimeRecord).where(TimeRecord.source_adjustment_id == adjustment.id))
        if record is None:
            record = TimeRecord(user_id=adjustment.user_id, record_type=adjustment.record_type,
                                record_datetime=to_app_timezone(datetime.combine(adjustment.target_date, adjustment.time)),
                                ip_address='ADJUSTMENT_APPROVED', source_adjustment_id=adjustment.id)
            db.add(record)
        else:
            record = await _latest_version(db, record.id)
            _restore(record)
        await db.flush()
        adjustment.applied_time_record_id = record.id

    async def revert(self, db, adjustment, manager_id):
        if adjustment.time is None:
            return
        record = await _matching_record(db, adjustment, False, created=True)
        if record is not None:
            _ignore(record, manager_id)


class DeletePunchAction(AdjustmentAction):
    async def apply(self, db, adjustment, manager_id):
        if adjustment.time is None:
            return
        record = await _matching_record(db, adjustment, False)
        if record is not None:
            adjustment.applied_time_record_id = record.id
            _ignore(record, manager_id)

    async def revert(self, db, adjustment, manager_id):
        if adjustment.time is None:
            return
        record = await _matching_record(db, adjustment, True)
        if record is not None:
            _restore(record)


_NO_PUNCH = NoPunchAction()
_ADD_PUNCH = AddPunchAction()
_ACTIONS = {
    AdjustmentType.EXTRA_TIME: _NO_PUNCH,
    AdjustmentType.WAIVER: _NO_PUNCH,
    AdjustmentType.DAILY_EXCESS: _NO_PUNCH,
    AdjustmentType.DELETE_PUNCH: DeletePunchAction(),
}


def adjustment_action(kind: AdjustmentType) -> AdjustmentAction:
    return _ACTIONS.get(kind, _ADD_PUNCH)
