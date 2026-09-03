from unittest.mock import MagicMock

import pytest
from app.features.payroll.payroll_models import PayrollClosure
from app.features.payroll.payroll_repository import (
    AsyncPayrollRepository,
    PayrollRepository,
)


def test_payroll_repository(db_session, normal_user):
    repo = PayrollRepository()

    created = repo.create(db_session, month=11, year=2026, user_id=normal_user.id)
    assert created.id is not None

    by_month = repo.get_by_month(db_session, 11, 2026)
    assert by_month.id == created.id

    all_res = repo.get_all(db_session, year=2026)
    assert len(all_res) >= 1

    repo.delete(db_session, 11, 2026, user_id=normal_user.id, observation="Reopened test")
    assert repo.get_by_month(db_session, 11, 2026) is None


@pytest.mark.asyncio
async def test_async_payroll_repository(async_db_mock):
    repo = AsyncPayrollRepository()
    created = PayrollClosure(id=1, month=11, year=2026, is_closed=True, closed_by_user_id=1)

    mock_scalars = MagicMock()
    mock_scalars.first.return_value = created
    mock_scalars.all.return_value = [created]
    async_db_mock.scalars.return_value = mock_scalars

    res_create = await repo.create(async_db_mock, month=11, year=2026, user_id=1)
    assert res_create.month == 11

    res_month = await repo.get_by_month(async_db_mock, 11, 2026)
    assert res_month.id == 1

    res_all = await repo.get_all(async_db_mock, year=2026)
    assert len(res_all) == 1

    await repo.delete(async_db_mock, 11, 2026, 1, "observation")


def test_payroll_repository_create_closure_variants(db_session, normal_user):
    repo = PayrollRepository()

    c1 = repo.create(db_session,
                     obj_in=PayrollClosure(month=1, year=2026, is_closed=True, closed_by_user_id=normal_user.id))
    assert c1.month == 1

    c2 = repo.create(db_session, obj_in={"month": 2, "year": 2026, "closed_by_user_id": normal_user.id})
    assert c2.month == 2

    class CustomClosure:
        month = 3
        year = 2026
        user_id = normal_user.id

    c3 = repo.create(db_session, obj_in=CustomClosure())
    assert c3.month == 3


@pytest.mark.asyncio
async def test_async_payroll_repository_create_closure_variants(async_db_mock):
    repo = AsyncPayrollRepository()

    c1 = await repo.create(async_db_mock,
                           obj_in=PayrollClosure(month=1, year=2026, is_closed=True, closed_by_user_id=1))
    assert c1.month == 1

    c2 = await repo.create(async_db_mock, obj_in={"month": 2, "year": 2026, "closed_by_user_id": 1})
    assert c2.month == 2

    class CustomClosure:
        month = 3
        year = 2026
        user_id = 1

    c3 = await repo.create(async_db_mock, obj_in=CustomClosure())
    assert c3.month == 3

    async_db_mock.scalars.return_value = object()
    assert await repo.get_by_month(async_db_mock, 99, 2026) is None
