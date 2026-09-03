from datetime import date
from unittest.mock import MagicMock

import pytest
from app.features.holidays.holiday_repository import AsyncHolidayRepository, HolidayRepository
from app.features.holidays.holiday_schemas import HolidayCreate


def test_holiday_repository(db_session):
    repo = HolidayRepository()
    d1 = date(2026, 12, 25)
    d2 = date(2026, 1, 1)

    h1 = repo.create(db_session, obj_in=HolidayCreate(date=d1, name="Christmas"))
    h2 = repo.create(db_session, obj_in=HolidayCreate(date=d2, name="New Year"))

    all_h = repo.get_all(db_session)
    assert len(all_h) >= 2

    by_date = repo.get_by_date(db_session, d1)
    assert by_date.name == "Christmas"

    by_id = repo.get_by_id(db_session, h1.id)
    assert by_id.id == h1.id

    by_month_dec = repo.get_by_month(db_session, 12, 2026)
    assert len(by_month_dec) >= 1

    by_month_jan = repo.get_by_month(db_session, 1, 2026)
    assert len(by_month_jan) >= 1

    repo.delete(db_session, h1.id)
    assert repo.get_by_id(db_session, h1.id) is None


@pytest.mark.asyncio
async def test_async_holiday_repository(async_db_mock):
    repo = AsyncHolidayRepository()
    d1 = date(2026, 12, 25)

    created = await repo.create(async_db_mock, obj_in=HolidayCreate(date=d1, name="Christmas"))
    assert created.name == "Christmas"

    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [created]
    mock_scalars.first.return_value = created
    async_db_mock.scalars.return_value = mock_scalars

    all_h = await repo.get_all(async_db_mock)
    assert len(all_h) == 1

    by_date = await repo.get_by_date(async_db_mock, d1)
    assert by_date == created

    async_db_mock.get.return_value = created
    by_id = await repo.get_by_id(async_db_mock, 1)
    assert by_id == created

    by_month = await repo.get_by_month(async_db_mock, 12, 2026)
    assert len(by_month) == 1

    by_month_non_dec = await repo.get_by_month(async_db_mock, 10, 2026)
    assert len(by_month_non_dec) == 1

    await repo.delete(async_db_mock, 1)
    async_db_mock.delete.assert_called_once()

