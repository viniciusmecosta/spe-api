import asyncio
from datetime import date, time
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.adjustments.adjustment_repository import AsyncAdjustmentRepository
from app.features.adjustments.adjustment_service import AdjustmentService
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import User
from app.features.adjustments.adjustment_schemas import AdjustmentWaiverCreate
from app.shared.enums import AdjustmentStatus, AdjustmentType, RecordType, UserRole

pytestmark = pytest.mark.asyncio


async def create_adjustment(factory):
    async with factory() as session:
        user = User(username='atomic', role=UserRole.MAINTAINER)
        session.add(user)
        await session.flush()
        request = AdjustmentRequest(user_id=user.id, adjustment_type=AdjustmentType.FORGOT_PUNCH,
                                    target_date=date(2026, 10, 22), time=time(8), record_type=RecordType.ENTRY)
        session.add(request)
        await session.commit()
        return user.id, request.id


async def test_concurrent_approvals_create_one_punch_and_revert_reuses_it(pg_session_factory):
    uid, rid = await create_adjustment(pg_session_factory)

    async def approve():
        async with pg_session_factory() as session:
            await AdjustmentService(session).approve_adjustment(request_id=rid, manager_id=uid)
    await asyncio.gather(approve(), approve())
    async with pg_session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(TimeRecord)) == 1
        service = AdjustmentService(session)
        await service.reject_adjustment(request_id=rid, manager_id=uid)
        record = await session.scalar(select(TimeRecord))
        assert record.is_ignored
        await service.approve_adjustment(request_id=rid, manager_id=uid)
        assert await session.scalar(select(func.count()).select_from(TimeRecord)) == 1
        await session.refresh(record)
        assert not record.is_ignored


async def test_failure_after_punch_creation_rolls_back_everything(pg_session_factory, monkeypatch):
    uid, rid = await create_adjustment(pg_session_factory)
    monkeypatch.setattr(AsyncAdjustmentRepository, 'update_status', AsyncMock(side_effect=RuntimeError('synthetic failure')))
    async with pg_session_factory() as session:
        with pytest.raises(RuntimeError):
            await AdjustmentService(session).approve_adjustment(request_id=rid, manager_id=uid)
    async with pg_session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(TimeRecord)) == 0
        assert (await session.get(AdjustmentRequest, rid)).status == AdjustmentStatus.PENDING


async def test_concurrent_waivers_cannot_exceed_existing_daily_limit(pg_session_factory):
    uid, rid = await create_adjustment(pg_session_factory)

    async def waive():
        async with pg_session_factory() as session:
            try:
                await AdjustmentService(session).create_manager_waiver(
                    waiver_in=AdjustmentWaiverCreate(user_id=uid, target_date=date(2026, 10, 23),
                                                    amount_hours=6, reason_text='Synthetic waiver'), manager_id=uid)
                return True
            except Exception as exc:
                assert getattr(exc, 'status_code', None) == 400
                return False
    assert sorted(await asyncio.gather(waive(), waive())) == [False, True]


async def test_reversal_follows_admin_edit_of_adjustment_punch(pg_session_factory):
    uid, rid = await create_adjustment(pg_session_factory)
    async with pg_session_factory() as session:
        service = AdjustmentService(session)
        await service.approve_adjustment(request_id=rid, manager_id=uid)
        original = await session.scalar(select(TimeRecord))
        original.is_ignored = True
        edited = TimeRecord(user_id=uid, record_type=original.record_type,
                            record_datetime=original.record_datetime.replace(minute=10),
                            original_record_id=original.id, ip_address=original.ip_address)
        session.add(edited)
        await session.commit()
        await service.reject_adjustment(request_id=rid, manager_id=uid)
        await session.refresh(edited)
        assert edited.is_ignored
        await service.approve_adjustment(request_id=rid, manager_id=uid)
        await session.refresh(original)
        await session.refresh(edited)
        assert original.is_ignored
        assert not edited.is_ignored
        assert await session.scalar(select(func.count()).select_from(TimeRecord)) == 2
