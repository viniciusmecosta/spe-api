from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.features.holidays.holiday_exceptions import HolidayAlreadyExistsError
from app.features.holidays.holiday_models import Holiday
from app.features.holidays.holiday_schemas import HolidayCreate
from app.features.holidays.holiday_service import holiday_service


@pytest.mark.asyncio
async def test_create_holiday_success(async_db_mock: AsyncMock, mocker: MagicMock) -> None:
    mocker.patch("app.features.holidays.holiday_service.payroll_service.async_validate_period_open",
                 new_callable=AsyncMock)
    mocker.patch("app.features.holidays.holiday_service.async_holiday_repository.get_by_date", new_callable=AsyncMock,
                 return_value=None)
    mock_holiday = Holiday(id=1, name="Ano Novo", date=date(2026, 1, 1))
    mocker.patch("app.features.holidays.holiday_service.async_holiday_repository.create", new_callable=AsyncMock,
                 return_value=mock_holiday)
    audit_mock = mocker.patch("app.features.holidays.holiday_service.audit_service.async_log_change",
                              new_callable=AsyncMock)

    payload = HolidayCreate(name="Ano Novo", date=date(2026, 1, 1))
    result = await holiday_service.create_holiday(async_db_mock, payload, current_user_id=1)

    assert result.id == 1
    assert result.name == "Ano Novo"
    audit_mock.assert_called_once()


@pytest.mark.asyncio
async def test_create_holiday_duplicate_date(async_db_mock: AsyncMock, mocker: MagicMock) -> None:
    mocker.patch("app.features.holidays.holiday_service.payroll_service.async_validate_period_open",
                 new_callable=AsyncMock)
    mocker.patch(
        "app.features.holidays.holiday_service.async_holiday_repository.get_by_date",
        new_callable=AsyncMock,
        return_value=Holiday(id=1, name="Existente", date=date(2026, 1, 1)),
    )

    payload = HolidayCreate(name="Outro Feriado", date=date(2026, 1, 1))
    with pytest.raises(HolidayAlreadyExistsError) as exc_info:
        await holiday_service.create_holiday(async_db_mock, payload, current_user_id=1)
    assert exc_info.value.status_code == 400
    assert "Já existe um feriado" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_all_holidays(async_db_mock: AsyncMock, mocker: MagicMock) -> None:
    holidays = [
        Holiday(id=1, name="Feriado 1", date=date(2026, 1, 1)),
        Holiday(id=2, name="Feriado 2", date=date(2026, 4, 21)),
    ]
    mocker.patch("app.features.holidays.holiday_service.async_holiday_repository.get_all", new_callable=AsyncMock,
                 return_value=holidays)

    result = await holiday_service.get_all_holidays(async_db_mock)
    assert len(result) == 2


@pytest.mark.asyncio
async def test_delete_holiday_exists(async_db_mock: AsyncMock, mocker: MagicMock) -> None:
    mock_holiday = Holiday(id=1, name="Ano Novo", date=date(2026, 1, 1))
    mocker.patch("app.features.holidays.holiday_service.async_holiday_repository.get_by_id", new_callable=AsyncMock,
                 return_value=mock_holiday)
    mocker.patch("app.features.holidays.holiday_service.payroll_service.async_validate_period_open",
                 new_callable=AsyncMock)
    delete_mock = mocker.patch("app.features.holidays.holiday_service.async_holiday_repository.delete",
                               new_callable=AsyncMock)
    audit_mock = mocker.patch("app.features.holidays.holiday_service.audit_service.async_log_change",
                              new_callable=AsyncMock)

    result = await holiday_service.delete_holiday(async_db_mock, holiday_id=1, current_user_id=1)
    assert result == {"status": "success"}
    delete_mock.assert_called_once_with(async_db_mock, 1)
    audit_mock.assert_called_once()


@pytest.mark.asyncio
async def test_delete_holiday_not_found(async_db_mock: AsyncMock, mocker: MagicMock) -> None:
    mocker.patch("app.features.holidays.holiday_service.async_holiday_repository.get_by_id", new_callable=AsyncMock,
                 return_value=None)
    delete_mock = mocker.patch("app.features.holidays.holiday_service.async_holiday_repository.delete",
                               new_callable=AsyncMock)

    result = await holiday_service.delete_holiday(async_db_mock, holiday_id=99, current_user_id=1)
    assert result == {"status": "success"}
    delete_mock.assert_not_called()
