from datetime import date
from unittest.mock import MagicMock

import pytest
from app.features.holidays.holiday_exceptions import HolidayAlreadyExistsError
from app.features.holidays.holiday_models import Holiday
from app.features.holidays.holiday_schemas import HolidayCreate
from app.features.holidays.holiday_service import holiday_service


def test_create_holiday_success(db_session_mock: MagicMock, mocker: MagicMock) -> None:
    mocker.patch("app.features.holidays.holiday_service.payroll_service.validate_period_open")
    mocker.patch("app.features.holidays.holiday_service.holiday_repository.get_by_date", return_value=None)
    mock_holiday = Holiday(id=1, name="Ano Novo", date=date(2026, 1, 1))
    mocker.patch("app.features.holidays.holiday_service.holiday_repository.create", return_value=mock_holiday)
    audit_mock = mocker.patch("app.features.holidays.holiday_service.audit_service.log_change")

    payload = HolidayCreate(name="Ano Novo", date=date(2026, 1, 1))
    result = holiday_service.create_holiday(db_session_mock, payload, current_user_id=1)

    assert result.id == 1
    assert result.name == "Ano Novo"
    audit_mock.assert_called_once()


def test_create_holiday_duplicate_date(db_session_mock: MagicMock, mocker: MagicMock) -> None:
    mocker.patch("app.features.holidays.holiday_service.payroll_service.validate_period_open")
    mocker.patch(
        "app.features.holidays.holiday_service.holiday_repository.get_by_date",
        return_value=Holiday(id=1, name="Existente", date=date(2026, 1, 1)),
    )

    payload = HolidayCreate(name="Outro Feriado", date=date(2026, 1, 1))
    with pytest.raises(HolidayAlreadyExistsError) as exc_info:
        holiday_service.create_holiday(db_session_mock, payload, current_user_id=1)
    assert exc_info.value.status_code == 400
    assert "Já existe um feriado" in exc_info.value.detail


def test_get_all_holidays(db_session_mock: MagicMock, mocker: MagicMock) -> None:
    holidays = [
        Holiday(id=1, name="Feriado 1", date=date(2026, 1, 1)),
        Holiday(id=2, name="Feriado 2", date=date(2026, 4, 21)),
    ]
    mocker.patch("app.features.holidays.holiday_service.holiday_repository.get_all", return_value=holidays)

    result = holiday_service.get_all_holidays(db_session_mock)
    assert len(result) == 2


def test_delete_holiday_exists(db_session_mock: MagicMock, mocker: MagicMock) -> None:
    mock_holiday = Holiday(id=1, name="Ano Novo", date=date(2026, 1, 1))
    mocker.patch("app.features.holidays.holiday_service.holiday_repository.get_by_id", return_value=mock_holiday)
    mocker.patch("app.features.holidays.holiday_service.payroll_service.validate_period_open")
    delete_mock = mocker.patch("app.features.holidays.holiday_service.holiday_repository.delete")
    audit_mock = mocker.patch("app.features.holidays.holiday_service.audit_service.log_change")

    result = holiday_service.delete_holiday(db_session_mock, holiday_id=1, current_user_id=1)
    assert result == {"status": "success"}
    delete_mock.assert_called_once_with(db_session_mock, 1)
    audit_mock.assert_called_once()


def test_delete_holiday_not_found(db_session_mock: MagicMock, mocker: MagicMock) -> None:
    mocker.patch("app.features.holidays.holiday_service.holiday_repository.get_by_id", return_value=None)
    delete_mock = mocker.patch("app.features.holidays.holiday_service.holiday_repository.delete")

    result = holiday_service.delete_holiday(db_session_mock, holiday_id=99, current_user_id=1)
    assert result == {"status": "success"}
    delete_mock.assert_not_called()
