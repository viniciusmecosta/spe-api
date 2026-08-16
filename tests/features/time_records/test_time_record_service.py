from datetime import datetime, timedelta, date
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

from fastapi import HTTPException, Request, status

import pytest
from app.core.config import settings
from app.shared.enums import RecordType, UserRole
from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.time_records.time_record_models import TimeRecord
from app.features.time_records.time_record_schemas import TimeRecordCreateAdmin, TimeRecordDeleteAdmin, TimeRecordUpdate
from app.features.time_records.time_record_service import time_record_service
from app.features.users.user_models import User


@pytest.fixture
def mock_user_repo():
    with patch("app.features.time_records.time_record_service.user_repository") as mock:
        yield mock

@pytest.fixture
def mock_time_record_repo():
    with patch("app.features.time_records.time_record_service.time_record_repository") as mock:
        yield mock

@pytest.fixture
def mock_payroll_service():
    with patch("app.features.time_records.time_record_service.payroll_service") as mock:
        yield mock

@pytest.fixture
def mock_audit_service():
    with patch("app.features.time_records.time_record_service.audit_service") as mock:
        yield mock

@pytest.fixture
def mock_get_client_ip():
    with patch("app.features.time_records.time_record_service.get_client_ip") as mock:
        yield mock

@pytest.fixture
def mock_get_client_device_name():
    with patch("app.features.time_records.time_record_service.get_client_device_name") as mock:
        yield mock


def test_get_my_records_and_list_records_for_admin(db_session_mock, mock_time_record_repo):
    mock_time_record_repo.get_all_by_user.return_value = ["rec1"]
    mock_time_record_repo.get_by_range.return_value = ["rec2"]
    
    assert time_record_service.get_my_records(db_session_mock, 1) == ["rec1"]
    assert time_record_service.list_records_for_admin(db_session_mock, 1, datetime(2026, 1, 1), datetime(2026, 1, 31)) == ["rec2"]


def test_trigger_auto_print_enabled(db_session_mock, mocker):
    mock_company = MagicMock()
    mock_company.auto_print_receipt = True
    mock_company.default_printer_id = 10
    mock_company.name = "Comp"
    mock_company.cnpj = "123"
    mocker.patch("app.features.companies.company_repository.company_repository.get_current", return_value=mock_company)
    
    mock_printer = MagicMock()
    mock_printer.status = True
    mocker.patch("app.features.printers.printer_repository.printer_repository.get_by_id", return_value=mock_printer)

    mock_bg = MagicMock()
    user = User(id=1, name="John", cpf="111", pis="222", auto_print_receipt=True)
    record = TimeRecord(id=1, user=user, record_datetime=datetime(2026, 1, 1, 12, 0, 0), device_name="Dev")
    
    time_record_service.trigger_auto_print(db_session_mock, record, mock_bg)
    mock_bg.add_task.assert_called_once()


def test_get_receipt_data_with_timeline(db_session_mock, mocker):
    mocker.patch("app.shared.hashid_service.hashid_service.decode", return_value=123)
    user = User(id=1, name="John", cpf="12345678900", pis="12345", role=UserRole.EMPLOYEE)
    mock_record = TimeRecord(id=123, user_id=1, user=user, record_datetime=datetime.now(ZoneInfo(settings.TIMEZONE)),
                             record_type=RecordType.ENTRY, device_name="Device 1")
    mocker.patch("app.features.time_records.time_record_service.time_record_repository.get", return_value=mock_record)
    mocker.patch("app.features.companies.company_repository.company_repository.get_current", return_value=None)
    
    timeline_mock = MagicMock()
    timeline_mock.action = "EDIT"
    timeline_mock.timestamp = datetime(2026, 1, 1)
    timeline_mock.user = user
    timeline_mock.old_data = {}
    timeline_mock.new_data = {}
    mocker.patch.object(time_record_service, "get_record_timeline", return_value=[timeline_mock])

    result = time_record_service.get_receipt_data(db_session_mock, "valid", user)
    assert len(result.timeline) == 1
    assert result.timeline[0].action == "EDIT"


def test_get_receipt_pdf_errors(db_session_mock, mocker):
    mocker.patch("app.shared.hashid_service.hashid_service.decode", return_value=None)
    user = User(id=1, role=UserRole.EMPLOYEE)
    with pytest.raises(HTTPException) as exc1:
        time_record_service.get_receipt_pdf(db_session_mock, "invalid", user)
    assert exc1.value.status_code == 404

    mocker.patch("app.shared.hashid_service.hashid_service.decode", return_value=123)
    mocker.patch("app.features.time_records.time_record_service.time_record_repository.get", return_value=None)
    with pytest.raises(HTTPException) as exc2:
        time_record_service.get_receipt_pdf(db_session_mock, "valid", user)
    assert exc2.value.status_code == 404

    mock_record = TimeRecord(id=123, user_id=2, record_type=RecordType.ENTRY)
    mocker.patch("app.features.time_records.time_record_service.time_record_repository.get", return_value=mock_record)
    with pytest.raises(HTTPException) as exc3:
        time_record_service.get_receipt_pdf(db_session_mock, "valid", user)
    assert exc3.value.status_code == 403


def test_validate_manual_punch_permission_user_not_found(db_session_mock, mock_user_repo):
    mock_user_repo.get.return_value = None
    request = MagicMock(spec=Request)
    with pytest.raises(HTTPException) as exc_info:
        time_record_service._validate_manual_punch_permission(db_session_mock, 1, request)
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Usuário não encontrado."

def test_validate_manual_punch_permission_manager(db_session_mock, mock_user_repo):
    user = User(id=1, role=UserRole.MANAGER)
    mock_user_repo.get.return_value = user
    request = MagicMock(spec=Request)
    time_record_service._validate_manual_punch_permission(db_session_mock, 1, request)

def test_validate_manual_punch_permission_mobile_allowed(db_session_mock, mock_user_repo):
    user = User(id=1, role=UserRole.EMPLOYEE, can_manual_punch_mobile=True)
    mock_user_repo.get.return_value = user
    request = MagicMock(spec=Request)
    request.headers.get.return_value = "mobile"
    time_record_service._validate_manual_punch_permission(db_session_mock, 1, request)

def test_validate_manual_punch_permission_mobile_forbidden(db_session_mock, mock_user_repo):
    user = User(id=1, role=UserRole.EMPLOYEE, can_manual_punch_mobile=False)
    mock_user_repo.get.return_value = user
    request = MagicMock(spec=Request)
    request.headers.get.return_value = "mobile"
    with pytest.raises(HTTPException) as exc_info:
        time_record_service._validate_manual_punch_permission(db_session_mock, 1, request)
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN

def test_validate_manual_punch_permission_desktop_allowed(db_session_mock, mock_user_repo):
    user = User(id=1, role=UserRole.EMPLOYEE, can_manual_punch_desktop=True)
    mock_user_repo.get.return_value = user
    request = MagicMock(spec=Request)
    request.headers.get.return_value = "desktop"
    time_record_service._validate_manual_punch_permission(db_session_mock, 1, request)

def test_validate_manual_punch_permission_desktop_forbidden(db_session_mock, mock_user_repo):
    user = User(id=1, role=UserRole.EMPLOYEE, can_manual_punch_desktop=False)
    mock_user_repo.get.return_value = user
    request = MagicMock(spec=Request)
    request.headers.get.return_value = "desktop"
    with pytest.raises(HTTPException) as exc_info:
        time_record_service._validate_manual_punch_permission(db_session_mock, 1, request)
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN


@patch.object(time_record_service, "_validate_manual_punch_permission")
@patch("app.features.time_records.time_record_service.trusted_time_service.get_trusted_time")
def test_register_entry_success(mock_get_trusted_time, mock_validate, db_session_mock, mock_payroll_service,
                                mock_get_client_ip, mock_get_client_device_name, mock_time_record_repo):
    current_time = datetime.now(ZoneInfo(settings.TIMEZONE))
    mock_get_trusted_time.return_value = (current_time, True)
    request = MagicMock(spec=Request)
    request.headers.get.return_value = "desktop"
    mock_get_client_ip.return_value = "127.0.0.1"
    mock_get_client_device_name.return_value = "TestDevice"
    record = TimeRecord(id=1, user_id=1, record_type=RecordType.ENTRY)
    mock_time_record_repo.create.return_value = record
    result = time_record_service.register_entry(db_session_mock, 1, request)
    assert result == record
    mock_validate.assert_called_once_with(db_session_mock, 1, request)
    mock_payroll_service.validate_period_open.assert_called_once_with(db_session_mock, current_time.date())
    mock_time_record_repo.create.assert_called_once_with(db_session_mock, 1, RecordType.ENTRY, current_time,
                                                         "127.0.0.1", "TestDevice", platform="desktop")


@patch.object(time_record_service, "_validate_manual_punch_permission")
@patch("app.features.time_records.time_record_service.trusted_time_service.get_trusted_time")
def test_register_entry_ntp_fallback(mock_get_trusted_time, mock_validate, db_session_mock, mock_payroll_service,
                                     mock_get_client_ip, mock_get_client_device_name, mock_time_record_repo,
                                     mock_audit_service):
    current_time = datetime.now(ZoneInfo(settings.TIMEZONE))
    mock_get_trusted_time.return_value = (current_time, False)
    request = MagicMock(spec=Request)
    request.headers.get.return_value = "desktop"
    mock_get_client_ip.return_value = "127.0.0.1"
    mock_get_client_device_name.return_value = "TestDevice"
    record = TimeRecord(id=1, user_id=1, record_type=RecordType.ENTRY)
    mock_time_record_repo.create.return_value = record
    result = time_record_service.register_entry(db_session_mock, 1, request)
    assert result == record
    assert result.edit_justification == "Registro feito com a hora local do servidor (Falha no NTP)."
    assert request.state.ntp_error is True
    db_session_mock.add.assert_called_once_with(record)
    db_session_mock.commit.assert_called_once()
    db_session_mock.refresh.assert_called_once_with(record)
    mock_audit_service.log_change.assert_called_once()


@patch.object(time_record_service, "_validate_manual_punch_permission")
@patch("app.features.time_records.time_record_service.trusted_time_service.get_trusted_time")
def test_register_exit_success(mock_get_trusted_time, mock_validate, db_session_mock, mock_payroll_service,
                               mock_get_client_ip, mock_get_client_device_name, mock_time_record_repo):
    current_time = datetime.now(ZoneInfo(settings.TIMEZONE))
    mock_get_trusted_time.return_value = (current_time, True)
    request = MagicMock(spec=Request)
    request.headers.get.return_value = "desktop"
    mock_get_client_ip.return_value = "127.0.0.1"
    mock_get_client_device_name.return_value = "TestDevice"
    record = TimeRecord(id=1, user_id=1, record_type=RecordType.EXIT)
    mock_time_record_repo.create.return_value = record
    result = time_record_service.register_exit(db_session_mock, 1, request)
    assert result == record
    mock_validate.assert_called_once_with(db_session_mock, 1, request)
    mock_payroll_service.validate_period_open.assert_called_once_with(db_session_mock, current_time.date())
    mock_time_record_repo.create.assert_called_once_with(db_session_mock, 1, RecordType.EXIT, current_time, "127.0.0.1",
                                                         "TestDevice", platform="desktop")


@patch.object(time_record_service, "_validate_manual_punch_permission")
@patch("app.features.time_records.time_record_service.trusted_time_service.get_trusted_time")
def test_register_exit_ntp_fallback(mock_get_trusted_time, mock_validate, db_session_mock, mock_payroll_service,
                                    mock_get_client_ip, mock_get_client_device_name, mock_time_record_repo,
                                    mock_audit_service):
    current_time = datetime.now(ZoneInfo(settings.TIMEZONE))
    mock_get_trusted_time.return_value = (current_time, False)
    request = MagicMock(spec=Request)
    request.headers.get.return_value = "desktop"
    mock_get_client_ip.return_value = "127.0.0.1"
    mock_get_client_device_name.return_value = "TestDevice"
    record = TimeRecord(id=1, user_id=1, record_type=RecordType.EXIT)
    mock_time_record_repo.create.return_value = record
    result = time_record_service.register_exit(db_session_mock, 1, request)
    assert result == record
    assert result.edit_justification == "Registro feito com a hora local do servidor (Falha no NTP)."
    assert request.state.ntp_error is True
    db_session_mock.add.assert_called_once_with(record)
    db_session_mock.commit.assert_called_once()
    db_session_mock.refresh.assert_called_once_with(record)
    mock_audit_service.log_change.assert_called_once()

def test_toggle_record_type_not_found(db_session_mock, mock_time_record_repo):
    mock_time_record_repo.get.return_value = None
    user = User(id=1, role=UserRole.EMPLOYEE)
    with pytest.raises(HTTPException) as exc_info:
        time_record_service.toggle_record_type(db_session_mock, 1, user)
    assert exc_info.value.status_code == status.HTTP_404_NOT_FOUND
    assert exc_info.value.detail == "Registro de ponto não encontrado."

def test_toggle_record_type_forbidden(db_session_mock, mock_time_record_repo):
    record = TimeRecord(id=1, user_id=2)
    mock_time_record_repo.get.return_value = record
    user = User(id=1, role=UserRole.EMPLOYEE)
    with pytest.raises(HTTPException) as exc_info:
        time_record_service.toggle_record_type(db_session_mock, 1, user)
    assert exc_info.value.status_code == status.HTTP_403_FORBIDDEN
    assert exc_info.value.detail == "Acesso negado."

def test_toggle_record_type_success(db_session_mock, mock_time_record_repo, mock_payroll_service, mock_audit_service):
    dt = datetime.now(ZoneInfo(settings.TIMEZONE))
    record = TimeRecord(id=1, user_id=1, record_type=RecordType.ENTRY, record_datetime=dt)
    mock_time_record_repo.get.return_value = record
    user = User(id=1, role=UserRole.MANAGER)
    result = time_record_service.toggle_record_type(db_session_mock, 1, user)
    assert result.record_type == RecordType.EXIT
    assert record.is_ignored is True
    assert result.original_record_id == 1
    assert result.edit_justification == "Inversão de marcação efetuada"
    assert result.is_verified is True
    db_session_mock.add.assert_any_call(result)
    db_session_mock.add.assert_any_call(record)
    db_session_mock.flush.assert_called_once()
    db_session_mock.commit.assert_called_once()
    db_session_mock.refresh.assert_called_once_with(result)
    mock_audit_service.log_change.assert_called_once()

def test_toggle_record_type_success_employee(db_session_mock, mock_time_record_repo, mock_payroll_service, mock_audit_service):
    dt = datetime.now(ZoneInfo(settings.TIMEZONE))
    record = TimeRecord(id=1, user_id=1, record_type=RecordType.EXIT, record_datetime=dt, original_record_id=5)
    mock_time_record_repo.get.return_value = record
    user = User(id=1, role=UserRole.EMPLOYEE)
    result = time_record_service.toggle_record_type(db_session_mock, 1, user)
    assert result.record_type == RecordType.ENTRY
    assert record.is_ignored is True
    assert result.original_record_id == 5
    assert result.is_verified is False

def test_create_admin_record(db_session_mock, mock_time_record_repo, mock_payroll_service, mock_audit_service):
    dt = datetime.now(ZoneInfo(settings.TIMEZONE))
    obj_in = TimeRecordCreateAdmin(user_id=1, record_type=RecordType.ENTRY, record_datetime=dt,
                                   edit_justification="Forgot")
    record = TimeRecord(id=1, user_id=1)
    mock_time_record_repo.create.return_value = record
    result = time_record_service.create_admin_record(db_session_mock, obj_in, manager_id=2, ip_address="127.0.0.1",
                                                     device_name="Dev")
    assert result == record
    assert result.edited_by == 2
    assert result.edit_justification == "Forgot"
    assert result.is_verified is True
    mock_time_record_repo.create.assert_called_once_with(db_session_mock, user_id=1, record_type=RecordType.ENTRY,
                                                         record_datetime=dt, ip_address="127.0.0.1", device_name="Dev",
                                                         platform="WEB_ADMIN")
    db_session_mock.add.assert_called_once_with(record)
    db_session_mock.commit.assert_called_once()
    db_session_mock.refresh.assert_called_once_with(record)
    mock_audit_service.log_change.assert_called_once()

def test_create_admin_record_no_device(db_session_mock, mock_time_record_repo, mock_payroll_service, mock_audit_service):
    dt = datetime.now(ZoneInfo(settings.TIMEZONE))
    obj_in = TimeRecordCreateAdmin(user_id=1, record_type=RecordType.ENTRY, record_datetime=dt, edit_justification="")
    record = TimeRecord(id=1, user_id=1)
    mock_time_record_repo.create.return_value = record
    time_record_service.create_admin_record(db_session_mock, obj_in, manager_id=2, ip_address="127.0.0.1",
                                            device_name=None)
    mock_time_record_repo.create.assert_called_once_with(db_session_mock, user_id=1, record_type=RecordType.ENTRY,
                                                         record_datetime=dt, ip_address="127.0.0.1", device_name="",
                                                         platform="WEB_ADMIN")

def test_update_admin_record_not_found(db_session_mock, mock_time_record_repo):
    mock_time_record_repo.get.return_value = None
    obj_in = TimeRecordUpdate(edit_justification="missing")
    with pytest.raises(HTTPException) as exc_info:
        time_record_service.update_admin_record(db_session_mock, 1, obj_in, 2)
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Registro não encontrado."

def test_update_admin_record_no_changes(db_session_mock, mock_time_record_repo, mock_payroll_service):
    dt = datetime.now(ZoneInfo(settings.TIMEZONE))
    record = TimeRecord(id=1, record_type=RecordType.ENTRY, record_datetime=dt)
    mock_time_record_repo.get.return_value = record
    obj_in = TimeRecordUpdate(edit_justification="")
    result = time_record_service.update_admin_record(db_session_mock, 1, obj_in, 2)
    assert result == record

def test_update_admin_record_with_changes(db_session_mock, mock_time_record_repo, mock_payroll_service, mock_audit_service):
    dt = datetime.now(ZoneInfo(settings.TIMEZONE))
    dt_new = datetime.now(ZoneInfo(settings.TIMEZONE))
    record = TimeRecord(id=1, user_id=1, record_type=RecordType.ENTRY, record_datetime=dt, edit_justification=None,
                        original_record_id=5)
    mock_time_record_repo.get.return_value = record
    obj_in = TimeRecordUpdate(record_type=RecordType.EXIT, record_datetime=dt_new, edit_justification="Fixed")
    result = time_record_service.update_admin_record(db_session_mock, 1, obj_in, 2, "1.1.1.1", "Dev", "Plat")
    assert result.record_type == RecordType.EXIT
    assert result.record_datetime == dt_new
    assert record.is_ignored is True
    assert result.original_record_id == 5
    assert result.edit_justification == "Fixed"
    assert result.is_verified is True
    assert result.ip_address == "1.1.1.1"
    assert result.device_name == "Dev"
    assert result.platform == "Plat"
    mock_payroll_service.validate_period_open.assert_any_call(db_session_mock, dt.date())
    mock_payroll_service.validate_period_open.assert_any_call(db_session_mock, dt_new.date())
    db_session_mock.add.assert_any_call(result)
    db_session_mock.add.assert_any_call(record)
    db_session_mock.commit.assert_called_once()
    db_session_mock.refresh.assert_called_once_with(result)
    mock_audit_service.log_change.assert_called_once()

def test_update_admin_record_no_device(db_session_mock, mock_time_record_repo, mock_payroll_service, mock_audit_service):
    dt = datetime.now(ZoneInfo(settings.TIMEZONE))
    record = TimeRecord(id=1, user_id=1, record_type=RecordType.ENTRY, record_datetime=dt)
    mock_time_record_repo.get.return_value = record
    obj_in = TimeRecordUpdate(record_type=RecordType.EXIT, edit_justification="")
    result = time_record_service.update_admin_record(db_session_mock, 1, obj_in, 2)
    assert result.device_name == ""

def test_delete_admin_record_not_found(db_session_mock, mock_time_record_repo):
    mock_time_record_repo.get.return_value = None
    obj_in = TimeRecordDeleteAdmin(edit_justification="Err")
    with pytest.raises(HTTPException) as exc_info:
        time_record_service.delete_admin_record(db_session_mock, 1, obj_in, 2)
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Registro não encontrado."

def test_delete_admin_record_success(db_session_mock, mock_time_record_repo, mock_payroll_service, mock_audit_service):
    dt = datetime.now(ZoneInfo(settings.TIMEZONE))
    record = TimeRecord(id=1, record_type=RecordType.ENTRY, record_datetime=dt)
    mock_time_record_repo.get.return_value = record
    obj_in = TimeRecordDeleteAdmin(edit_justification="Mistake")
    time_record_service.delete_admin_record(db_session_mock, 1, obj_in, 2)
    mock_payroll_service.validate_period_open.assert_called_once_with(db_session_mock, dt.date())
    mock_time_record_repo.delete.assert_called_once_with(db_session_mock, 1, 2)
    mock_audit_service.log_change.assert_called_once()

def test_delete_admin_record_no_justification(db_session_mock, mock_time_record_repo, mock_payroll_service, mock_audit_service):
    dt = datetime.now(ZoneInfo(settings.TIMEZONE))
    record = TimeRecord(id=1, record_type=RecordType.ENTRY, record_datetime=dt)
    mock_time_record_repo.get.return_value = record
    obj_in = TimeRecordDeleteAdmin(edit_justification="")
    time_record_service.delete_admin_record(db_session_mock, 1, obj_in, 2)
    mock_audit_service.log_change.assert_called_once()
    call_args = mock_audit_service.log_change.call_args[1]
    assert call_args["new_data"]["justification"] == ""


@patch("app.features.time_records.time_record_service.get_client_device_name")
def test_create_punch_first_record(mock_get_device, db_session_mock, mock_time_record_repo):
    mock_time_record_repo.get_last_by_user.return_value = None
    mock_get_device.return_value = "Dev"
    dt = datetime.now(ZoneInfo(settings.TIMEZONE))
    record = TimeRecord(id=1)
    mock_time_record_repo.create.return_value = record
    result = time_record_service.create_punch(db_session_mock, 1, dt, "1.1.1.1")
    assert result == record
    mock_time_record_repo.create.assert_called_once_with(db_session_mock, user_id=1, record_type=RecordType.ENTRY,
                                                         record_datetime=dt, ip_address="1.1.1.1", device_name="Dev",
                                                         platform="desktop", biometric_id=None)


@patch("app.features.time_records.time_record_service.get_client_device_name")
def test_create_punch_same_day_exit(mock_get_device, db_session_mock, mock_time_record_repo):
    dt_last = datetime.now(ZoneInfo(settings.TIMEZONE))
    last_record = TimeRecord(id=1, record_type=RecordType.ENTRY, record_datetime=dt_last)
    mock_time_record_repo.get_last_by_user.return_value = last_record
    mock_get_device.return_value = "Dev"
    dt_curr = dt_last
    mock_time_record_repo.create.return_value = TimeRecord(id=2)
    time_record_service.create_punch(db_session_mock, 1, dt_curr, "1.1.1.1", biometric_id=123)
    mock_time_record_repo.create.assert_called_once_with(db_session_mock, user_id=1, record_type=RecordType.EXIT,
                                                         record_datetime=dt_curr, ip_address="1.1.1.1",
                                                         device_name="Dev", platform="desktop", biometric_id=123)


@patch("app.features.time_records.time_record_service.get_client_device_name")
def test_create_punch_different_day(mock_get_device, db_session_mock, mock_time_record_repo):
    dt_last = datetime(2023, 1, 1, tzinfo=ZoneInfo("UTC"))
    last_record = TimeRecord(id=1, record_type=RecordType.ENTRY, record_datetime=dt_last)
    mock_time_record_repo.get_last_by_user.return_value = last_record
    dt_curr = datetime(2023, 1, 2, tzinfo=ZoneInfo("UTC"))
    mock_time_record_repo.create.return_value = TimeRecord(id=2)
    time_record_service.create_punch(db_session_mock, 1, dt_curr, "1.1.1.1")
    mock_time_record_repo.create.assert_called_once_with(db_session_mock, user_id=1, record_type=RecordType.ENTRY,
                                                         record_datetime=dt_curr, ip_address="1.1.1.1",
                                                         device_name=mock_get_device.return_value, platform="desktop",
                                                         biometric_id=None)


@patch("app.features.time_records.time_record_service.get_client_device_name")
def test_create_punch_naive_datetimes(mock_get_device, db_session_mock, mock_time_record_repo):
    dt_last = datetime(2023, 1, 1, 12, 0)
    last_record = TimeRecord(id=1, record_type=RecordType.ENTRY, record_datetime=dt_last)
    mock_time_record_repo.get_last_by_user.return_value = last_record
    dt_curr = datetime(2023, 1, 1, 10, 0)
    mock_time_record_repo.create.return_value = TimeRecord(id=2)
    time_record_service.create_punch(db_session_mock, 1, dt_curr, "1.1.1.1")
    mock_time_record_repo.create.assert_called_once_with(db_session_mock, user_id=1, record_type=RecordType.EXIT,
                                                         record_datetime=dt_curr, ip_address="1.1.1.1",
                                                         device_name=mock_get_device.return_value, platform="desktop",
                                                         biometric_id=None)

def test_get_record_timeline(db_session_mock, mock_time_record_repo):
    records = [TimeRecord(id=1), TimeRecord(id=2)]
    mock_time_record_repo.get_timeline.return_value = records
    result = time_record_service.get_record_timeline(db_session_mock, 1)
    assert result == records
    mock_time_record_repo.get_timeline.assert_called_once_with(db_session_mock, 1)


def test_invalidate_extra_time_requests(db_session_mock):
    mock_query = MagicMock()
    mock_filter = MagicMock()
    db_session_mock.query.return_value = mock_query
    mock_query.filter.return_value = mock_filter
    req1 = AdjustmentRequest(id=1)
    req2 = AdjustmentRequest(id=2)
    mock_filter.all.return_value = [req1, req2]
    time_record_service._invalidate_extra_time_requests(db_session_mock, 1, date(2023, 1, 1))
    assert db_session_mock.delete.call_count == 2
    db_session_mock.flush.assert_called_once()


def test_is_first_entry_affected_no_entries(db_session_mock):
    mock_query = MagicMock()
    mock_filter = MagicMock()
    mock_order = MagicMock()
    db_session_mock.query.return_value = mock_query
    mock_query.filter.return_value = mock_filter
    mock_filter.order_by.return_value = mock_order
    mock_order.first.return_value = None
    result = time_record_service._is_first_entry_affected(db_session_mock, 1, date(2023, 1, 1))
    assert result is False
    result2 = time_record_service._is_first_entry_affected(db_session_mock, 1, date(2023, 1, 1),
                                                           new_datetime=datetime.now(ZoneInfo("UTC")))
    assert result2 is True


def test_is_first_entry_affected_matches_record_id(db_session_mock):
    first_entry = TimeRecord(id=10, record_datetime=datetime(2023, 1, 1, 8, 0, tzinfo=ZoneInfo("UTC")))
    mock_query = MagicMock()
    mock_filter = MagicMock()
    mock_order = MagicMock()
    db_session_mock.query.return_value = mock_query
    mock_query.filter.return_value = mock_filter
    mock_filter.order_by.return_value = mock_order
    mock_order.first.return_value = first_entry
    result = time_record_service._is_first_entry_affected(db_session_mock, 1, date(2023, 1, 1), record_id=10)
    assert result is True


def test_is_first_entry_affected_new_datetime_earlier(db_session_mock):
    first_entry = TimeRecord(id=10, record_datetime=datetime(2023, 1, 1, 8, 0, tzinfo=ZoneInfo("UTC")))
    mock_query = MagicMock()
    mock_filter = MagicMock()
    mock_order = MagicMock()
    db_session_mock.query.return_value = mock_query
    mock_query.filter.return_value = mock_filter
    mock_filter.order_by.return_value = mock_order
    mock_order.first.return_value = first_entry
    new_dt = datetime(2023, 1, 1, 7, 0, tzinfo=ZoneInfo("UTC"))
    result = time_record_service._is_first_entry_affected(db_session_mock, 1, date(2023, 1, 1), new_datetime=new_dt)
    assert result is True


def test_is_first_entry_affected_new_datetime_later(db_session_mock):
    first_entry = TimeRecord(id=10, record_datetime=datetime(2023, 1, 1, 8, 0, tzinfo=ZoneInfo("UTC")))
    mock_query = MagicMock()
    mock_filter = MagicMock()
    mock_order = MagicMock()
    db_session_mock.query.return_value = mock_query
    mock_query.filter.return_value = mock_filter
    mock_filter.order_by.return_value = mock_order
    mock_order.first.return_value = first_entry
    new_dt = datetime(2023, 1, 1, 9, 0, tzinfo=ZoneInfo("UTC"))
    result = time_record_service._is_first_entry_affected(db_session_mock, 1, date(2023, 1, 1), new_datetime=new_dt)
    assert result is False


@patch.object(time_record_service, "_is_first_entry_affected")
@patch.object(time_record_service, "_invalidate_extra_time_requests")
def test_toggle_record_type_invalidates_first_entry(mock_invalidate, mock_is_first, db_session_mock,
                                                    mock_time_record_repo, mock_payroll_service, mock_audit_service):
    dt = datetime.now(ZoneInfo(settings.TIMEZONE))
    record = TimeRecord(id=1, user_id=1, record_type=RecordType.ENTRY, record_datetime=dt)
    mock_time_record_repo.get.return_value = record
    user = User(id=1, role=UserRole.MANAGER)
    mock_is_first.return_value = True
    time_record_service.toggle_record_type(db_session_mock, 1, user)
    mock_is_first.assert_called_with(db_session_mock, 1, dt.date(), record_id=1)
    mock_invalidate.assert_called_once_with(db_session_mock, 1, dt.date())


@patch.object(time_record_service, "_is_first_entry_affected")
@patch.object(time_record_service, "_invalidate_extra_time_requests")
def test_toggle_record_type_invalidates_new_entry(mock_invalidate, mock_is_first, db_session_mock,
                                                  mock_time_record_repo, mock_payroll_service, mock_audit_service):
    dt = datetime.now(ZoneInfo(settings.TIMEZONE))
    record = TimeRecord(id=1, user_id=1, record_type=RecordType.EXIT, record_datetime=dt)
    mock_time_record_repo.get.return_value = record
    user = User(id=1, role=UserRole.MANAGER)
    mock_is_first.return_value = True
    time_record_service.toggle_record_type(db_session_mock, 1, user)
    mock_is_first.assert_called_with(db_session_mock, 1, dt.date(), new_datetime=dt)
    mock_invalidate.assert_called_once_with(db_session_mock, 1, dt.date())


@patch.object(time_record_service, "_is_first_entry_affected")
@patch.object(time_record_service, "_invalidate_extra_time_requests")
def test_create_admin_record_invalidates(mock_invalidate, mock_is_first, db_session_mock, mock_time_record_repo,
                                         mock_payroll_service, mock_audit_service):
    dt = datetime.now(ZoneInfo(settings.TIMEZONE))
    obj_in = TimeRecordCreateAdmin(user_id=1, record_type=RecordType.ENTRY, record_datetime=dt,
                                   edit_justification="Forgot")
    mock_is_first.return_value = True
    time_record_service.create_admin_record(db_session_mock, obj_in, manager_id=2, ip_address="127.0.0.1",
                                            device_name="Dev")
    mock_is_first.assert_called_with(db_session_mock, 1, dt.date(), new_datetime=dt)
    mock_invalidate.assert_called_once_with(db_session_mock, 1, dt.date())


@patch.object(time_record_service, "_is_first_entry_affected")
@patch.object(time_record_service, "_invalidate_extra_time_requests")
def test_update_admin_record_invalidates_old_date(mock_invalidate, mock_is_first, db_session_mock,
                                                  mock_time_record_repo, mock_payroll_service, mock_audit_service):
    dt = datetime.now(ZoneInfo(settings.TIMEZONE))
    dt_new = datetime.now(ZoneInfo(settings.TIMEZONE)) + timedelta(hours=1)
    record = TimeRecord(id=1, user_id=1, record_type=RecordType.ENTRY, record_datetime=dt, edit_justification=None)
    mock_time_record_repo.get.return_value = record
    obj_in = TimeRecordUpdate(record_type=RecordType.EXIT, record_datetime=dt_new, edit_justification="Fixed")
    mock_is_first.side_effect = [True, False]
    mock_audit_service.compute_diffs.return_value = ({}, {})
    time_record_service.update_admin_record(db_session_mock, 1, obj_in, 2)
    mock_invalidate.assert_any_call(db_session_mock, 1, dt.date())


@patch.object(time_record_service, "_is_first_entry_affected")
@patch.object(time_record_service, "_invalidate_extra_time_requests")
def test_update_admin_record_invalidates_new_date(mock_invalidate, mock_is_first, db_session_mock,
                                                  mock_time_record_repo, mock_payroll_service, mock_audit_service):
    dt = datetime.now(ZoneInfo(settings.TIMEZONE))
    dt_new = datetime.now(ZoneInfo(settings.TIMEZONE)) + timedelta(hours=1)
    record = TimeRecord(id=1, user_id=1, record_type=RecordType.EXIT, record_datetime=dt, edit_justification=None)
    mock_time_record_repo.get.return_value = record
    obj_in = TimeRecordUpdate(record_type=RecordType.ENTRY, record_datetime=dt_new, edit_justification="Fixed")
    mock_is_first.side_effect = [True]
    mock_audit_service.compute_diffs.return_value = ({}, {})
    time_record_service.update_admin_record(db_session_mock, 1, obj_in, 2)
    mock_invalidate.assert_any_call(db_session_mock, 1, dt_new.date())


@patch.object(time_record_service, "_is_first_entry_affected")
@patch.object(time_record_service, "_invalidate_extra_time_requests")
def test_delete_admin_record_invalidates(mock_invalidate, mock_is_first, db_session_mock, mock_time_record_repo,
                                         mock_payroll_service, mock_audit_service):
    dt = datetime.now(ZoneInfo(settings.TIMEZONE))
    record = TimeRecord(id=1, user_id=1, record_type=RecordType.ENTRY, record_datetime=dt)
    mock_time_record_repo.get.return_value = record
    obj_in = TimeRecordDeleteAdmin(edit_justification="Mistake")
    mock_is_first.return_value = True
    time_record_service.delete_admin_record(db_session_mock, 1, obj_in, 2)
    mock_is_first.assert_called_with(db_session_mock, 1, dt.date(), record_id=1)
    mock_invalidate.assert_called_once_with(db_session_mock, 1, dt.date())


def test_get_receipt_data_invalid_hashid(db_session_mock, mocker):
    mocker.patch("app.shared.hashid_service.hashid_service.decode", return_value=None)
    user = User(id=1, role=UserRole.EMPLOYEE)
    with pytest.raises(HTTPException) as exc_info:
        time_record_service.get_receipt_data(db_session_mock, "invalid", user)
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Invalid receipt ID"


def test_get_receipt_data_record_not_found(db_session_mock, mocker):
    mocker.patch("app.shared.hashid_service.hashid_service.decode", return_value=123)
    mocker.patch("app.features.time_records.time_record_service.time_record_repository.get", return_value=None)
    user = User(id=1, role=UserRole.EMPLOYEE)
    with pytest.raises(HTTPException) as exc_info:
        time_record_service.get_receipt_data(db_session_mock, "valid", user)
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Record not found"


def test_get_receipt_data_forbidden_employee(db_session_mock, mocker):
    mocker.patch("app.shared.hashid_service.hashid_service.decode", return_value=123)
    mock_record = TimeRecord(id=123, user_id=2, user=User(id=2, name="Other", cpf="111", pis="222"),
                             record_datetime=datetime.now(ZoneInfo(settings.TIMEZONE)), record_type=RecordType.ENTRY)
    mocker.patch("app.features.time_records.time_record_service.time_record_repository.get", return_value=mock_record)
    user = User(id=1, role=UserRole.EMPLOYEE)
    with pytest.raises(HTTPException) as exc_info:
        time_record_service.get_receipt_data(db_session_mock, "valid", user)
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "Not allowed to view this receipt"


def test_get_receipt_data_success(db_session_mock, mocker):
    mocker.patch("app.shared.hashid_service.hashid_service.decode", return_value=123)
    user = User(id=1, name="John", cpf="12345678900", pis="12345", role=UserRole.EMPLOYEE)
    mock_record = TimeRecord(id=123, user_id=1, user=user, record_datetime=datetime.now(ZoneInfo(settings.TIMEZONE)),
                             record_type=RecordType.ENTRY, device_name="Device 1")
    mocker.patch("app.features.time_records.time_record_service.time_record_repository.get", return_value=mock_record)
    mocker.patch("app.features.companies.company_repository.company_repository.get_current", return_value=None)
    mocker.patch.object(time_record_service, "get_record_timeline", return_value=[])

    result = time_record_service.get_receipt_data(db_session_mock, "valid", user)
    assert result.short_id == "valid"
    assert result.record_id == 123
    assert result.employee_name == "John"


def test_get_receipt_pdf_success(db_session_mock, mocker):
    mocker.patch("app.shared.hashid_service.hashid_service.decode", return_value=123)
    user = User(id=1, name="John", cpf="12345678900", pis="12345", role=UserRole.MANAGER)
    mock_record = TimeRecord(id=123, user_id=1, user=user, record_datetime=datetime.now(ZoneInfo(settings.TIMEZONE)),
                             record_type=RecordType.ENTRY, device_name="Device 1")
    mocker.patch("app.features.time_records.time_record_service.time_record_repository.get", return_value=mock_record)
    mocker.patch("app.features.companies.company_repository.company_repository.get_current", return_value=None)
    mocker.patch("app.features.time_records.receipt_service.receipt_service.generate_pdf_receipt",
                 return_value=b"%PDF-1.4...")

    pdf_bytes, filename = time_record_service.get_receipt_pdf(db_session_mock, "valid", user)
    assert pdf_bytes == b"%PDF-1.4..."
    assert filename == "123.pdf"


def test_trigger_auto_print_disabled(db_session_mock, mocker):
    mock_company = MagicMock()
    mock_company.auto_print_receipt = False
    mocker.patch("app.features.companies.company_repository.company_repository.get_current", return_value=mock_company)
    mock_bg = MagicMock()

    user = User(id=1, name="John", auto_print_receipt=None)
    record = TimeRecord(id=1, user=user)
    time_record_service.trigger_auto_print(db_session_mock, record, mock_bg)
    mock_bg.add_task.assert_not_called()
