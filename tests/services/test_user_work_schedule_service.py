import pytest
from datetime import date, timedelta
from fastapi import HTTPException
from unittest.mock import MagicMock, patch, PropertyMock

from app.domain.models.user import User, UserWorkScheduleConfig
from app.services.user_work_schedule_service import UserWorkScheduleService

@pytest.fixture
def service():
    return UserWorkScheduleService()

@pytest.fixture
def user():
    u = User(id=1)
    u.historical_schedules = []
    return u

def test_check_payroll_closure_no_valid_until(service, db_session_mock):
    with patch('app.services.user_work_schedule_service.payroll_repository') as mock_payroll_repo:
        mock_payroll_repo.get_by_month.return_value = None
        service.check_payroll_closure(db_session_mock, date(2023, 1, 15))
        assert mock_payroll_repo.get_by_month.called

def test_check_payroll_closure_with_valid_until(service, db_session_mock):
    with patch('app.services.user_work_schedule_service.payroll_repository') as mock_payroll_repo:
        mock_payroll_repo.get_by_month.return_value = None
        service.check_payroll_closure(db_session_mock, date(2023, 1, 15), date(2023, 3, 15))
        assert mock_payroll_repo.get_by_month.call_count == 3

def test_check_payroll_closure_closed_raises_error(service, db_session_mock):
    with patch('app.services.user_work_schedule_service.payroll_repository') as mock_payroll_repo:
        closure = MagicMock()
        closure.is_closed = True
        mock_payroll_repo.get_by_month.return_value = closure
        with pytest.raises(HTTPException) as exc:
            service.check_payroll_closure(db_session_mock, date(2023, 1, 15))
        assert exc.value.status_code == 403
        assert "já está fechada" in exc.value.detail

def test_check_payroll_closure_year_wrap(service, db_session_mock):
    with patch('app.services.user_work_schedule_service.payroll_repository') as mock_payroll_repo:
        mock_payroll_repo.get_by_month.return_value = None
        service.check_payroll_closure(db_session_mock, date(2023, 12, 1), date(2024, 1, 31))
        assert mock_payroll_repo.get_by_month.call_count == 2
        mock_payroll_repo.get_by_month.assert_any_call(db_session_mock, 12, 2023)
        mock_payroll_repo.get_by_month.assert_any_call(db_session_mock, 1, 2024)

def test_handle_schedule_overlap_no_overlap(service, user):
    sch1 = UserWorkScheduleConfig(id=1, day_of_week=1, valid_from=date(2023, 1, 1), valid_until=date(2023, 1, 31))
    user.historical_schedules.append(sch1)
    service.handle_schedule_overlap(user, 1, date(2023, 2, 1), date(2023, 2, 28))
    assert sch1.valid_until == date(2023, 1, 31)

def test_handle_schedule_overlap_different_day(service, user):
    sch1 = UserWorkScheduleConfig(id=1, day_of_week=1, valid_from=date(2023, 1, 1), valid_until=date(2023, 1, 31))
    user.historical_schedules.append(sch1)
    service.handle_schedule_overlap(user, 2, date(2023, 1, 15), date(2023, 2, 15))
    assert sch1.valid_until == date(2023, 1, 31)

def test_handle_schedule_overlap_ignore_id(service, user):
    sch1 = UserWorkScheduleConfig(id=1, day_of_week=1, valid_from=date(2023, 1, 1), valid_until=date(2023, 1, 31))
    user.historical_schedules.append(sch1)
    service.handle_schedule_overlap(user, 1, date(2023, 1, 15), date(2023, 2, 15), ignore_id=1)
    assert sch1.valid_until == date(2023, 1, 31)

def test_handle_schedule_overlap_adjusts_valid_until(service, user):
    sch1 = UserWorkScheduleConfig(id=1, day_of_week=1, valid_from=date(2023, 1, 1), valid_until=None)
    user.historical_schedules.append(sch1)
    with pytest.raises(HTTPException) as exc:
        service.handle_schedule_overlap(user, 1, date(2023, 2, 1), None)
    assert exc.value.status_code == 400
    assert "Já existe um expediente vigente" in exc.value.detail

def test_handle_schedule_overlap_raises_error(service, user):
    sch1 = UserWorkScheduleConfig(id=1, day_of_week=1, valid_from=date(2023, 2, 1), valid_until=None)
    user.historical_schedules.append(sch1)
    with pytest.raises(HTTPException) as exc:
        service.handle_schedule_overlap(user, 1, date(2023, 1, 1), date(2023, 2, 15))
    assert exc.value.status_code == 400
    assert "Já existe um expediente vigente" in exc.value.detail

def test_extract_schedule_data(service):
    sch = UserWorkScheduleConfig(
        day_of_week=1, daily_hours=8.0, valid_from=date(2023, 1, 1), valid_until=date(2023, 1, 31),
        entry_1="08:00:00", exit_1="12:00:00", entry_2="13:00:00", exit_2="17:00:00"
    )
    data = service._extract_schedule_data(sch)
    assert data["day_of_week"] == 1
    assert data["daily_hours"] == 8.0
    assert data["valid_from"] == "2023-01-01"
    assert data["valid_until"] == "2023-01-31"
    assert data["entry_1"] == "08:00:00"
    assert data["exit_1"] == "12:00:00"
    assert data["entry_2"] == "13:00:00"
    assert data["exit_2"] == "17:00:00"

def test_extract_schedule_data_none_values(service):
    sch = UserWorkScheduleConfig(day_of_week=1, daily_hours=8.0)
    data = service._extract_schedule_data(sch)
    assert data["valid_from"] is None
    assert data["entry_1"] is None

def test_apply_schedule_updates(service):
    sch = UserWorkScheduleConfig(day_of_week=1, daily_hours=8.0)
    sch_data = {
        'day_of_week': 2,
        'daily_hours': 9.0,
        'entry_1': '09:00:00',
        'exit_1': '13:00:00',
        'entry_2': '14:00:00',
        'exit_2': '18:00:00'
    }
    service._apply_schedule_updates(sch, sch_data, date(2023, 1, 1), date(2023, 1, 31))
    assert sch.day_of_week == 2
    assert sch.daily_hours == 9.0
    assert sch.entry_1 == '09:00:00'
    assert sch.valid_from == date(2023, 1, 1)

def test_apply_schedule_updates_from_obj(service):
    sch = UserWorkScheduleConfig(day_of_week=1, daily_hours=8.0)
    sch_data = MagicMock(day_of_week=2, daily_hours=9.0, entry_1='09:00:00', exit_1='13:00:00', entry_2='14:00:00', exit_2='18:00:00')
    service._apply_schedule_updates_from_obj(sch, sch_data, date(2023, 1, 1), date(2023, 1, 31))
    assert sch.day_of_week == 2
    assert sch.daily_hours == 9.0
    assert sch.entry_1 == '09:00:00'
    assert sch.valid_from == date(2023, 1, 1)

def test_remove_stale_schedules(service, db_session_mock, user):
    sch1 = UserWorkScheduleConfig(id=1, valid_from=date(2023, 1, 1), valid_until=date(2023, 1, 31))
    sch2 = UserWorkScheduleConfig(id=2, valid_from=date(2023, 2, 1), valid_until=date(2023, 2, 28))
    user.historical_schedules = [sch1, sch2]
    with patch('app.domain.models.user.User.current_schedules', new_callable=PropertyMock) as mock_current:
        mock_current.return_value = [sch1, sch2]
        with patch.object(service, 'check_payroll_closure') as mock_check:
            sch_data = MagicMock(id=1)
            service._remove_stale_schedules(db_session_mock, user, [sch_data])
            
            assert sch1 in user.historical_schedules
            assert sch2 not in user.historical_schedules
            mock_check.assert_called_once_with(db_session_mock, date(2023, 2, 1), date(2023, 2, 28))

def test_create_new_schedule_is_create_true(service, db_session_mock, user):
    sch_data = MagicMock(day_of_week=1, daily_hours=8.0, entry_1='08:00', exit_1='12:00', entry_2='13:00', exit_2='17:00')
    with patch.object(service, 'check_payroll_closure') as mock_check, patch.object(service, 'handle_schedule_overlap') as mock_handle:
        service._create_new_schedule(db_session_mock, user, sch_data, date(2023, 1, 1), date(2023, 1, 31), date(2023, 1, 1), True)
        assert len(user.historical_schedules) == 1
        assert user.historical_schedules[0].day_of_week == 1
        assert user.historical_schedules[0].entry_1 == '08:00'
        mock_check.assert_not_called()
        mock_handle.assert_called_once()

def test_create_new_schedule_is_create_false(service, db_session_mock, user):
    sch_data = MagicMock(day_of_week=1, daily_hours=8.0, entry_1='08:00', exit_1='12:00', entry_2='13:00', exit_2='17:00')
    with patch.object(service, 'check_payroll_closure') as mock_check, patch.object(service, 'handle_schedule_overlap') as mock_handle:
        service._create_new_schedule(db_session_mock, user, sch_data, None, date(2023, 1, 31), date(2023, 1, 1), False)
        mock_check.assert_called_once_with(db_session_mock, date(2023, 1, 1), date(2023, 1, 31))

def test_handle_existing_schedule(service, db_session_mock, user):
    existing_sch = UserWorkScheduleConfig(id=1, valid_from=date(2023, 1, 1), valid_until=date(2023, 1, 31))
    sch_data = MagicMock(day_of_week=1, daily_hours=8.0)
    with patch.object(service, 'check_payroll_closure') as mock_check, \
         patch.object(service, 'handle_schedule_overlap') as mock_handle, \
         patch.object(service, '_apply_schedule_updates_from_obj') as mock_apply:
        
        service._handle_existing_schedule(db_session_mock, user, existing_sch, sch_data, 1, date(2023, 2, 1), date(2023, 2, 28), date(2023, 2, 1))
        
        assert mock_check.call_count == 2
        mock_handle.assert_called_once()
        mock_apply.assert_called_once()

def test_handle_existing_schedule_no_valid_from(service, db_session_mock, user):
    existing_sch = UserWorkScheduleConfig(id=1, valid_from=date(2023, 1, 1), valid_until=date(2023, 1, 31))
    sch_data = MagicMock(day_of_week=1, daily_hours=8.0)
    with patch.object(service, 'check_payroll_closure') as mock_check, \
         patch.object(service, 'handle_schedule_overlap') as mock_handle, \
         patch.object(service, '_apply_schedule_updates_from_obj') as mock_apply:
        
        service._handle_existing_schedule(db_session_mock, user, existing_sch, sch_data, 1, None, date(2023, 2, 28), date(2023, 2, 1))
        
        assert mock_check.call_count == 2

def test_process_single_schedule_invalid_hours(service, db_session_mock, user):
    sch_data = MagicMock(daily_hours=25)
    with pytest.raises(HTTPException) as exc:
        service._process_single_schedule(db_session_mock, user, sch_data, True)
    assert exc.value.status_code == 400
    
    sch_data = MagicMock(daily_hours=-1)
    with pytest.raises(HTTPException) as exc:
        service._process_single_schedule(db_session_mock, user, sch_data, True)
    assert exc.value.status_code == 400

def test_process_single_schedule_existing_not_create(service, db_session_mock, user):
    sch1 = UserWorkScheduleConfig(id=1)
    user.historical_schedules = [sch1]
    sch_data = MagicMock(id=1, daily_hours=8.0, valid_from=None, valid_until=None)
    with patch.object(service, '_handle_existing_schedule') as mock_handle:
        service._process_single_schedule(db_session_mock, user, sch_data, False)
        mock_handle.assert_called_once()

def test_process_single_schedule_existing_not_found(service, db_session_mock, user):
    sch1 = UserWorkScheduleConfig(id=1)
    user.historical_schedules = [sch1]
    sch_data = MagicMock(id=2, daily_hours=8.0, valid_from=None, valid_until=None)
    with patch.object(service, '_create_new_schedule') as mock_create, \
         patch.object(service, '_handle_existing_schedule') as mock_handle:
        service._process_single_schedule(db_session_mock, user, sch_data, False)
        mock_create.assert_not_called()
        mock_handle.assert_not_called()

def test_process_single_schedule_is_create(service, db_session_mock, user):
    sch_data = MagicMock(id=1, daily_hours=8.0, valid_from=None, valid_until=None)
    with patch.object(service, '_create_new_schedule') as mock_create:
        service._process_single_schedule(db_session_mock, user, sch_data, True)
        mock_create.assert_called_once()

def test_sync_user_schedules_none(service, db_session_mock, user):
    service.sync_user_schedules(db_session_mock, user, None)

def test_sync_user_schedules_create(service, db_session_mock, user):
    with patch.object(service, '_remove_stale_schedules') as mock_remove, \
         patch.object(service, '_process_single_schedule') as mock_process:
        
        service.sync_user_schedules(db_session_mock, user, [MagicMock()], is_create=True)
        mock_remove.assert_not_called()
        mock_process.assert_called_once()

def test_sync_user_schedules_update(service, db_session_mock, user):
    with patch.object(service, '_remove_stale_schedules') as mock_remove, \
         patch.object(service, '_process_single_schedule') as mock_process:
        
        service.sync_user_schedules(db_session_mock, user, [MagicMock()], is_create=False)
        mock_remove.assert_called_once()
        mock_process.assert_called_once()

def test_add_schedule_user_not_found(service, db_session_mock):
    with patch('app.services.user_work_schedule_service.user_repository') as mock_user_repo:
        mock_user_repo.get.return_value = None
        with pytest.raises(HTTPException) as exc:
            service.add_schedule(db_session_mock, 1, {}, 2)
        assert exc.value.status_code == 404

def test_add_schedule_success(service, db_session_mock, user):
    with patch('app.services.user_work_schedule_service.user_repository') as mock_user_repo, \
         patch('app.services.user_work_schedule_service.audit_service') as mock_audit_service, \
         patch.object(service, 'check_payroll_closure') as mock_check, \
         patch.object(service, 'handle_schedule_overlap') as mock_handle:
        
        mock_user_repo.get.return_value = user
        sch_data = {'day_of_week': 1, 'daily_hours': 8.0, 'valid_from': date(2023, 1, 1), 'valid_until': date(2023, 1, 31)}
        new_sch = service.add_schedule(db_session_mock, 1, sch_data, 2)
        
        db_session_mock.add.assert_called_once()
        db_session_mock.commit.assert_called_once()
        db_session_mock.refresh.assert_called_once()
        mock_audit_service.log.assert_called_once()
        assert new_sch.user_id == 1

def test_add_schedule_no_valid_from(service, db_session_mock, user):
    with patch('app.services.user_work_schedule_service.user_repository') as mock_user_repo, \
         patch('app.services.user_work_schedule_service.audit_service') as mock_audit_service, \
         patch.object(service, 'check_payroll_closure') as mock_check, \
         patch.object(service, 'handle_schedule_overlap') as mock_handle:
        
        mock_user_repo.get.return_value = user
        sch_data = {'day_of_week': 1, 'daily_hours': 8.0}
        new_sch = service.add_schedule(db_session_mock, 1, sch_data, 2)
        assert new_sch.valid_from == date.today()

def test_update_schedule_not_found(service, db_session_mock):
    db_session_mock.query.return_value.items = []
    with pytest.raises(HTTPException) as exc:
        service.update_schedule(db_session_mock, 1, 1, {}, 2)
    assert exc.value.status_code == 404

def test_update_schedule_success(service, db_session_mock, user):
    sch = UserWorkScheduleConfig(id=1, user_id=1, valid_from=date(2023, 1, 1), valid_until=date(2023, 1, 31), day_of_week=1, daily_hours=8.0)
    db_session_mock.query.return_value.items = [sch]
    
    with patch('app.services.user_work_schedule_service.user_repository') as mock_user_repo, \
         patch('app.services.user_work_schedule_service.audit_service') as mock_audit_service, \
         patch.object(service, 'check_payroll_closure') as mock_check, \
         patch.object(service, 'handle_schedule_overlap') as mock_handle:
        
        mock_user_repo.get.return_value = user
        mock_audit_service.compute_diffs.return_value = ({}, {})
        
        sch_data = {'day_of_week': 2, 'daily_hours': 9.0}
        updated_sch = service.update_schedule(db_session_mock, 1, 1, sch_data, 2)
        
        db_session_mock.add.assert_called_once()
        db_session_mock.commit.assert_called_once()
        db_session_mock.refresh.assert_called_once()
        mock_audit_service.log.assert_called_once()
        assert updated_sch.day_of_week == 2

def test_delete_schedule_not_found(service, db_session_mock):
    db_session_mock.query.return_value.items = []
    with pytest.raises(HTTPException) as exc:
        service.delete_schedule(db_session_mock, 1, 1, 2)
    assert exc.value.status_code == 404

def test_delete_schedule_success(service, db_session_mock):
    sch = UserWorkScheduleConfig(id=1, user_id=1, valid_from=date(2023, 1, 1), valid_until=date(2023, 1, 31), day_of_week=1, daily_hours=8.0)
    db_session_mock.query.return_value.items = [sch]
    
    with patch('app.services.user_work_schedule_service.audit_service') as mock_audit_service, \
         patch.object(service, 'check_payroll_closure') as mock_check:
        
        service.delete_schedule(db_session_mock, 1, 1, 2)
        
        db_session_mock.delete.assert_called_once_with(sch)
        db_session_mock.commit.assert_called_once()
        mock_audit_service.log.assert_called_once()
