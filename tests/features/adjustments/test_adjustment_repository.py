from datetime import date
from unittest.mock import MagicMock

import pytest
from app.features.adjustments.adjustment_repository import (
    AdjustmentRepository,
    AsyncAdjustmentRepository,
)
from app.features.adjustments.adjustment_schemas import AdjustmentRequestCreate
from app.shared.enums import AdjustmentStatus, AdjustmentType


def test_adjustment_repository_all_methods(db_session, normal_user):
    repo = AdjustmentRepository()

    obj_in = AdjustmentRequestCreate(
        adjustment_type=AdjustmentType.WAIVER,
        target_date=date(2026, 8, 1),
        amount_hours=2.0,
        reason_text="Doctor appointment",
    )
    created = repo.create(db_session, user_id=normal_user.id, obj_in=obj_in)
    assert created.id is not None

    fetched = repo.get(db_session, created.id)
    assert fetched is not None

    user_all = repo.get_all_by_user(
        db_session,
        user_id=normal_user.id,
        month=8,
        year=2026,
        status="PENDING",
        order_by="target_date",
        order_direction="asc",
    )
    assert len(user_all) >= 1

    user_all_not_pending = repo.get_all_by_user(
        db_session,
        user_id=normal_user.id,
        status="NOT_PENDING",
    )
    assert isinstance(user_all_not_pending, list)

    user_all_year = repo.get_all_by_user(
        db_session,
        user_id=normal_user.id,
        year=2026,
    )
    assert len(user_all_year) >= 1

    all_reqs = repo.get_all(
        db_session,
        month=8,
        year=2026,
        status="PENDING",
        order_by="target_date",
        order_direction="asc",
    )
    assert len(all_reqs) >= 1

    all_reqs_year = repo.get_all(
        db_session,
        year=2026,
        status="NOT_PENDING",
    )
    assert isinstance(all_reqs_year, list)

    pending_count = repo.count_pending(db_session, from_date=date(2026, 1, 1))
    assert pending_count >= 1

    updated = repo.update_status(db_session, created, AdjustmentStatus.APPROVED, manager_id=normal_user.id,
                                 comment="Approved")
    assert updated.status == AdjustmentStatus.APPROVED

    waivers = repo.get_waivers_by_user_and_date(db_session, normal_user.id, date(2026, 8, 1))
    assert len(waivers) >= 1

    att = repo.create_attachment(db_session, created.id, "/tmp/test.pdf", "pdf")
    assert att.id is not None

    repo.soft_delete(db_session, created.id, normal_user.id)
    assert repo.get(db_session, created.id) is None

    repo.delete(db_session, created.id)


@pytest.mark.asyncio
async def test_async_adjustment_repository(async_db_mock):
    repo = AsyncAdjustmentRepository()
    obj_in = AdjustmentRequestCreate(
        adjustment_type=AdjustmentType.WAIVER,
        target_date=date(2026, 8, 1),
        amount_hours=2.0,
        reason_text="Doctor appointment",
    )
    created = await repo.create(async_db_mock, user_id=1, obj_in=obj_in)
    assert created.user_id == 1

    mock_scalars = MagicMock()
    mock_scalars.first.return_value = created
    mock_scalars.all.return_value = [created]
    async_db_mock.scalars.return_value = mock_scalars
    async_db_mock.scalar.return_value = 1

    assert await repo.get(async_db_mock, 1) == created
    assert len(await repo.get_all_by_user(async_db_mock, 1, month=8, year=2026, status="PENDING")) == 1
    assert len(await repo.get_all(async_db_mock, month=8, year=2026, status="NOT_PENDING")) == 1
    assert await repo.count_pending(async_db_mock, from_date=date(2026, 1, 1)) == 1
    assert len(await repo.get_waivers_by_user_and_date(async_db_mock, 1, date(2026, 8, 1))) == 1

    updated = await repo.update_status(async_db_mock, created, AdjustmentStatus.APPROVED, 1, "Approved")
    assert updated.status == AdjustmentStatus.APPROVED

    att = await repo.create_attachment(async_db_mock, 1, "/tmp/test.pdf", "pdf")
    assert att.file_path == "/tmp/test.pdf"

    await repo.soft_delete(async_db_mock, 1, 1)
    await repo.delete(async_db_mock, 1)
