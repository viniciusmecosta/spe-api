import pytest
from unittest.mock import MagicMock, patch
from datetime import date
from fastapi import HTTPException
from app.services.user_work_schedule_service import user_work_schedule_service
from app.domain.models.user import User, UserWorkScheduleConfig

def test_check_payroll_closure_ok(db_session_mock, mocker):
    mocker.patch("app.repositories.payroll_repository.payroll_repository.get_by_month", return_value=None)
    user_work_schedule_service.check_payroll_closure(db_session_mock, date(2026, 9, 1), date(2026, 9, 30))

def test_check_payroll_closure_closed(db_session_mock, mocker):
    closure = MagicMock()
    closure.is_closed = True
    mocker.patch("app.repositories.payroll_repository.payroll_repository.get_by_month", return_value=closure)
    with pytest.raises(HTTPException) as exc:
        user_work_schedule_service.check_payroll_closure(db_session_mock, date(2026, 9, 1), date(2026, 9, 30))
    assert exc.value.status_code == 400

def test_bulk_add_schedules_success(db_session_mock, mocker):
    mocker.patch.object(user_work_schedule_service, "check_payroll_closure")
    
    user = User(id=1, name="Test User")
    mocker.patch("app.repositories.user_repository.user_repository.get", return_value=user)
    mocker.patch.object(user_work_schedule_service, "handle_schedule_overlap")
    mocker.patch("app.services.audit_service.audit_service.log")

    bulk_data = {
        "valid_from": date(2026, 9, 1),
        "valid_until": date(2026, 9, 30),
        "users": [
            {
                "user_id": 1,
                "schedules": [
                    {"day_of_week": 1, "daily_hours": 8.0}
                ]
            }
        ]
    }

    res = user_work_schedule_service.bulk_add_schedules(db_session_mock, bulk_data, 99)
    assert "sucesso" in res["message"]
    db_session_mock.add.assert_called()
    db_session_mock.commit.assert_called()

def test_bulk_add_schedules_missing_dates(db_session_mock):
    bulk_data = {}
    with pytest.raises(HTTPException) as exc:
        user_work_schedule_service.bulk_add_schedules(db_session_mock, bulk_data, 99)
    assert exc.value.status_code == 400

def test_bulk_add_schedules_exceeds_duration(db_session_mock):
    bulk_data = {
        "valid_from": date(2026, 9, 1),
        "valid_until": date(2026, 11, 30),
        "users": []
    }
    with pytest.raises(HTTPException) as exc:
        user_work_schedule_service.bulk_add_schedules(db_session_mock, bulk_data, 99)
    assert exc.value.status_code == 400

def test_update_bulk_schedules_success(db_session_mock, mocker):
    mocker.patch.object(user_work_schedule_service, "check_payroll_closure")
    mocker.patch("app.services.audit_service.audit_service.log")
    
    old_cfg = UserWorkScheduleConfig(id=10, user_id=1, day_of_week=1, valid_from=date(2026, 9, 1), valid_until=date(2026, 9, 30))
    mock_query = mocker.MagicMock()
    mock_filter = mocker.MagicMock()
    mock_all = mocker.MagicMock()
    db_session_mock.query.return_value = mock_query
    mock_query.filter.return_value = mock_filter
    mock_filter.all.return_value = [old_cfg]
    
    user = User(id=1, name="Test User")
    mocker.patch("app.repositories.user_repository.user_repository.get", return_value=user)
    mocker.patch.object(user_work_schedule_service, "handle_schedule_overlap")
    
    bulk_data = {
        "valid_from": date(2026, 9, 1),
        "valid_until": date(2026, 9, 30),
        "users": [
            {
                "user_id": 1,
                "schedules": [
                    {"day_of_week": 1, "daily_hours": 9.0}
                ]
            }
        ]
    }
    
    res = user_work_schedule_service.update_bulk_schedules(db_session_mock, date(2026, 9, 1), date(2026, 9, 30), bulk_data, 99)
    assert res["message"] == "Expedientes atualizados com sucesso."

def test_delete_bulk_schedules_success(db_session_mock, mocker):
    mocker.patch.object(user_work_schedule_service, "check_payroll_closure")
    mocker.patch("app.services.audit_service.audit_service.log")
    
    old_cfg = UserWorkScheduleConfig(id=10, user_id=1, day_of_week=1, valid_from=date(2026, 9, 1), valid_until=date(2026, 9, 30))
    mock_query = mocker.MagicMock()
    mock_filter = mocker.MagicMock()
    mock_all = mocker.MagicMock()
    db_session_mock.query.return_value = mock_query
    mock_query.filter.return_value = mock_filter
    mock_filter.all.return_value = [old_cfg]
    
    res = user_work_schedule_service.delete_bulk_schedules(db_session_mock, date(2026, 9, 1), date(2026, 9, 30), 99)
    assert "sucesso" in res["message"]
    db_session_mock.delete.assert_called_with(old_cfg)
