import pytest
from datetime import date, datetime, time
from unittest.mock import MagicMock
from fastapi import HTTPException, UploadFile
from io import BytesIO
from app.services.adjustment_service import adjustment_service
from app.domain.models.adjustment import AdjustmentRequest
from app.domain.models.enums import AdjustmentStatus, AdjustmentType, RecordType
from app.domain.models.time_record import TimeRecord
from app.schemas.adjustment import AdjustmentRequestCreate, AdjustmentWaiverCreate

def test_enrich_adjustments_with_records(db_session_mock):
    adj1 = AdjustmentRequest(id=1, user_id=1, target_date=date(2023, 10, 1))
    adj2 = AdjustmentRequest(id=2, user_id=1, target_date=date(2023, 10, 2))
    
    tr1 = TimeRecord(user_id=1, record_datetime=datetime(2023, 10, 1, 8, 0))
    db_session_mock.query.return_value.items = [tr1]
    
    res = adjustment_service._enrich_adjustments_with_records(db_session_mock, [adj1, adj2])
    assert len(res) == 2
    assert len(res[0].time_records) == 1
    assert len(res[1].time_records) == 0

def test_validate_waiver_limit_ok(db_session_mock, mocker):
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.get_waivers_by_user_and_date", return_value=[AdjustmentRequest(amount_hours=2.0)])
    adjustment_service._validate_waiver_limit(db_session_mock, 1, date(2023, 10, 1), 5.0)

def test_validate_waiver_limit_exceeded(db_session_mock, mocker):
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.get_waivers_by_user_and_date", return_value=[AdjustmentRequest(amount_hours=8.0)])
    with pytest.raises(HTTPException) as exc:
        adjustment_service._validate_waiver_limit(db_session_mock, 1, date(2023, 10, 1), 5.0)
    assert exc.value.status_code == 400

def test_create_adjustment_request(db_session_mock, mocker):
    mocker.patch("app.services.payroll_service.payroll_service.validate_period_open")
    mocker.patch("app.services.adjustment_service.AdjustmentService._validate_waiver_limit")
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.create", return_value=AdjustmentRequest(id=1, user_id=1, target_date=date(2023, 10, 1)))
    mocker.patch("app.services.adjustment_service.AdjustmentService._enrich_adjustments_with_records", return_value=[AdjustmentRequest(id=1)])
    
    obj_in = AdjustmentRequestCreate(adjustment_type=AdjustmentType.WAIVER, target_date=date(2023, 10, 1), amount_hours=2.0, reason_text="teste")
    res = adjustment_service.create_adjustment_request(db_session_mock, 1, obj_in)
    assert res.id == 1

def test_create_manager_waiver(db_session_mock, mocker):
    mocker.patch("app.services.payroll_service.payroll_service.validate_period_open")
    mocker.patch("app.services.adjustment_service.AdjustmentService._validate_waiver_limit")
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.create")
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.update_status", return_value=AdjustmentRequest(id=1, user_id=1, target_date=date(2023, 10, 1)))
    mocker.patch("app.services.adjustment_service.AdjustmentService._enrich_adjustments_with_records", return_value=[AdjustmentRequest(id=1)])
    mocker.patch("app.services.audit_service.audit_service.log")
    
    obj_in = AdjustmentWaiverCreate(user_id=1, target_date=date(2023, 10, 1), amount_hours=8.0, reason_text="teste")
    res = adjustment_service.create_manager_waiver(db_session_mock, obj_in, 99)
    assert res.id == 1

def test_admin_delete_adjustment(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, adjustment_type=AdjustmentType.EXTRA_TIME, target_date=date(2023, 10, 1), status=AdjustmentStatus.APPROVED)
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.get", return_value=request)
    mocker.patch("app.services.payroll_service.payroll_service.validate_period_open")
    mocker.patch("app.services.adjustment_service.AdjustmentService._revert_adjustment_action")
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.soft_delete")
    mocker.patch("app.services.audit_service.audit_service.log")
    
    adjustment_service.admin_delete_adjustment(db_session_mock, 1, 99, "Justificativa teste")

def test_delete_adjustment_not_found(db_session_mock, mocker):
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.get", return_value=None)
    with pytest.raises(HTTPException) as exc:
        adjustment_service.delete_adjustment(db_session_mock, 1, 99, "Justificativa teste")
    assert exc.value.status_code == 404

def test_approve_adjustment(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, target_date=date(2023, 10, 1), adjustment_type=AdjustmentType.FORGOT_PUNCH, status=AdjustmentStatus.PENDING)
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.get", return_value=request)
    mocker.patch("app.services.payroll_service.payroll_service.validate_period_open")
    mocker.patch("app.services.adjustment_service.AdjustmentService._execute_adjustment_action")
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.update_status", return_value=AdjustmentRequest(id=1, status=AdjustmentStatus.APPROVED))
    mocker.patch("app.services.audit_service.audit_service.compute_diffs", return_value=({"status": "PENDING"}, {"status": "APPROVED"}))
    mocker.patch("app.services.audit_service.audit_service.log")
    mocker.patch("app.services.adjustment_service.AdjustmentService._enrich_adjustments_with_records", return_value=[AdjustmentRequest(id=1, status=AdjustmentStatus.APPROVED)])
    
    res = adjustment_service.approve_adjustment(db_session_mock, 1, 99)
    assert res.status == AdjustmentStatus.APPROVED

def test_approve_adjustment_waiver_no_attachment(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, target_date=date(2023, 10, 1), adjustment_type=AdjustmentType.WAIVER, attachments=[])
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.get", return_value=request)
    mocker.patch("app.services.payroll_service.payroll_service.validate_period_open")
    with pytest.raises(HTTPException) as exc:
        adjustment_service.approve_adjustment(db_session_mock, 1, 99)
    assert exc.value.status_code == 400

def test_reject_adjustment(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, target_date=date(2023, 10, 1), status=AdjustmentStatus.PENDING)
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.get", return_value=request)
    mocker.patch("app.services.payroll_service.payroll_service.validate_period_open")
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.update_status", return_value=AdjustmentRequest(id=1, status=AdjustmentStatus.REJECTED))
    mocker.patch("app.services.audit_service.audit_service.compute_diffs", return_value=({"status": "PENDING"}, {"status": "REJECTED"}))
    mocker.patch("app.services.audit_service.audit_service.log")
    mocker.patch("app.services.adjustment_service.AdjustmentService._enrich_adjustments_with_records", return_value=[AdjustmentRequest(id=1, status=AdjustmentStatus.REJECTED)])
    
    res = adjustment_service.reject_adjustment(db_session_mock, 1, 99, "comentario")
    assert res.status == AdjustmentStatus.REJECTED

def test_execute_adjustment_action_create(db_session_mock, mocker):
    request = AdjustmentRequest(user_id=1, target_date=date(2023, 10, 1), time=time(8, 0), adjustment_type=AdjustmentType.FORGOT_PUNCH, record_type=RecordType.ENTRY)
    mocker.patch("app.repositories.time_record_repository.time_record_repository.create")
    adjustment_service._execute_adjustment_action(db_session_mock, request, 99)

def test_execute_adjustment_action_delete(db_session_mock, mocker):
    request = AdjustmentRequest(user_id=1, target_date=date(2023, 10, 1), time=time(8, 0), adjustment_type=AdjustmentType.DELETE_PUNCH, record_type=RecordType.ENTRY)
    record = TimeRecord(id=1)
    db_session_mock.query.return_value.items = [record]
    mocker.patch("app.repositories.time_record_repository.get_local_time")
    
    adjustment_service._execute_adjustment_action(db_session_mock, request, 99)
    assert record.is_ignored is True

def test_revert_adjustment_action(db_session_mock, mocker):
    request = AdjustmentRequest(user_id=1, target_date=date(2023, 10, 1), time=time(8, 0), adjustment_type=AdjustmentType.FORGOT_PUNCH, record_type=RecordType.ENTRY)
    record = TimeRecord(id=1)
    db_session_mock.query.return_value.items = [record]
    mocker.patch("app.repositories.time_record_repository.get_local_time")
    
    adjustment_service._revert_adjustment_action(db_session_mock, request, 99)
    assert record.is_ignored is True

def test_revert_adjustment_status(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, target_date=date(2023, 10, 1), status=AdjustmentStatus.APPROVED, adjustment_type=AdjustmentType.FORGOT_PUNCH)
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.get", return_value=request)
    mocker.patch("app.services.payroll_service.payroll_service.validate_period_open")
    mocker.patch("app.services.adjustment_service.AdjustmentService._revert_adjustment_action")
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.update_status", return_value=AdjustmentRequest(id=1, status=AdjustmentStatus.PENDING))
    mocker.patch("app.services.audit_service.audit_service.compute_diffs", return_value=({"status": "APPROVED"}, {"status": "PENDING"}))
    mocker.patch("app.services.audit_service.audit_service.log")
    mocker.patch("app.services.adjustment_service.AdjustmentService._enrich_adjustments_with_records", return_value=[AdjustmentRequest(id=1, status=AdjustmentStatus.PENDING)])
    
    res = adjustment_service.revert_adjustment_status(db_session_mock, 1, 99, AdjustmentStatus.PENDING, "motivo")
    assert res.status == AdjustmentStatus.PENDING

def test_enrich_adjustments_with_records_empty(db_session_mock):
    res = adjustment_service._enrich_adjustments_with_records(db_session_mock, [])
    assert res == []

def test_validate_waiver_limit_no_amount(db_session_mock):
    adjustment_service._validate_waiver_limit(db_session_mock, 1, date(2023, 10, 1), None)

def test_get_all_enriched(db_session_mock, mocker):
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.get_all", return_value=[])
    mocker.patch("app.services.adjustment_service.AdjustmentService._enrich_adjustments_with_records", return_value=[])
    assert adjustment_service.get_all_enriched(db_session_mock) == []

def test_get_my_enriched(db_session_mock, mocker):
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.get_all_by_user", return_value=[])
    mocker.patch("app.services.adjustment_service.AdjustmentService._enrich_adjustments_with_records", return_value=[])
    assert adjustment_service.get_my_enriched(db_session_mock, 1) == []

def test_admin_delete_adjustment_not_found(db_session_mock, mocker):
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.get", return_value=None)
    with pytest.raises(HTTPException) as exc:
        adjustment_service.admin_delete_adjustment(db_session_mock, 1, 99, "Justificativa teste")
    assert exc.value.status_code == 404

def test_delete_adjustment_success(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, adjustment_type=AdjustmentType.EXTRA_TIME, target_date=date(2023, 10, 1), status=AdjustmentStatus.APPROVED)
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.get", return_value=request)
    mocker.patch("app.services.payroll_service.payroll_service.validate_period_open")
    mocker.patch("app.services.adjustment_service.AdjustmentService._revert_adjustment_action")
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.soft_delete")
    mocker.patch("app.services.audit_service.audit_service.log")
    
    adjustment_service.delete_adjustment(db_session_mock, 1, 99, "Justificativa teste")

def test_delete_extra_time_adjustment_success(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, adjustment_type=AdjustmentType.EXTRA_TIME, target_date=date(2023, 10, 1), status=AdjustmentStatus.APPROVED)
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.get", return_value=request)
    mocker.patch("app.services.payroll_service.payroll_service.validate_period_open")
    mocker.patch("app.services.adjustment_service.AdjustmentService._revert_adjustment_action")
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.soft_delete")
    mock_audit_log = mocker.patch("app.services.audit_service.audit_service.log")
    
    adjustment_service.delete_adjustment(db_session_mock, 1, 99, "Justificativa exclusao hora extra")
    mock_audit_log.assert_called_once()
    assert mock_audit_log.call_args[1]["action"] == "DELETE_ADJUSTMENT"
    assert mock_audit_log.call_args[1]["new_data"] == {"reason": "Justificativa exclusao hora extra"}

def test_delete_waiver_adjustment_success(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, adjustment_type=AdjustmentType.WAIVER, target_date=date(2023, 10, 1), status=AdjustmentStatus.APPROVED)
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.get", return_value=request)
    mocker.patch("app.services.payroll_service.payroll_service.validate_period_open")
    mocker.patch("app.services.adjustment_service.AdjustmentService._revert_adjustment_action")
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.soft_delete")
    mock_audit_log = mocker.patch("app.services.audit_service.audit_service.log")
    
    adjustment_service.delete_adjustment(db_session_mock, 1, 99, "Justificativa exclusao abono")
    mock_audit_log.assert_called_once()
    assert mock_audit_log.call_args[1]["action"] == "DELETE_ADJUSTMENT"
    assert mock_audit_log.call_args[1]["new_data"] == {"reason": "Justificativa exclusao abono"}
    assert mock_audit_log.call_args[1]["new_data"] == {"reason": "Justificativa exclusao abono"}

def test_delete_adjustment_wrong_type_blocked(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, adjustment_type=AdjustmentType.PUNCH_NOT_COUNTED, target_date=date(2023, 10, 1), status=AdjustmentStatus.APPROVED)
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.get", return_value=request)
    mocker.patch("app.services.payroll_service.payroll_service.validate_period_open")
    mock_soft_delete = mocker.patch("app.repositories.adjustment_repository.adjustment_repository.soft_delete")
    
    with pytest.raises(HTTPException) as exc:
        adjustment_service.delete_adjustment(db_session_mock, 1, 99, "Justificativa teste")
    assert exc.value.status_code == 400
    assert "WAIVER" in exc.value.detail
    mock_soft_delete.assert_not_called()

def test_admin_delete_adjustment_wrong_type_blocked(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, adjustment_type=AdjustmentType.FORGOT_PUNCH, target_date=date(2023, 10, 1), status=AdjustmentStatus.APPROVED)
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.get", return_value=request)
    mocker.patch("app.services.payroll_service.payroll_service.validate_period_open")
    mock_soft_delete = mocker.patch("app.repositories.adjustment_repository.adjustment_repository.soft_delete")
    
    with pytest.raises(HTTPException) as exc:
        adjustment_service.admin_delete_adjustment(db_session_mock, 1, 99, "Justificativa teste")
    assert exc.value.status_code == 400
    assert "WAIVER" in exc.value.detail
    mock_soft_delete.assert_not_called()

def test_upload_attachment_not_found(db_session_mock, mocker):
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.get", return_value=None)
    with pytest.raises(HTTPException) as exc:
        adjustment_service.upload_attachment(db_session_mock, 1, UploadFile(filename="test.png", file=BytesIO(b"")), 1)
    assert exc.value.status_code == 404

def test_upload_attachment_forbidden(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, user_id=2)
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.get", return_value=request)
    with pytest.raises(HTTPException) as exc:
        adjustment_service.upload_attachment(db_session_mock, 1, UploadFile(filename="test.png", file=BytesIO(b"")), 1)
    assert exc.value.status_code == 403

def test_upload_attachment_invalid_name(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, user_id=1, target_date=date(2023, 10, 1))
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.get", return_value=request)
    mocker.patch("app.services.payroll_service.payroll_service.validate_period_open")
    with pytest.raises(HTTPException) as exc:
        adjustment_service.upload_attachment(db_session_mock, 1, UploadFile(filename="test", file=BytesIO(b"")), 1)
    assert exc.value.status_code == 400

def test_upload_attachment_invalid_ext(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, user_id=1, target_date=date(2023, 10, 1))
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.get", return_value=request)
    mocker.patch("app.services.payroll_service.payroll_service.validate_period_open")
    with pytest.raises(HTTPException) as exc:
        adjustment_service.upload_attachment(db_session_mock, 1, UploadFile(filename="test.txt", file=BytesIO(b"")), 1)
    assert exc.value.status_code == 400

def test_upload_attachment_invalid_content(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, user_id=1, target_date=date(2023, 10, 1))
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.get", return_value=request)
    mocker.patch("app.services.payroll_service.payroll_service.validate_period_open")
    with pytest.raises(HTTPException) as exc:
        adjustment_service.upload_attachment(db_session_mock, 1, UploadFile(filename="test.png", file=BytesIO(b"invalid")), 1)
    assert exc.value.status_code == 400

def test_upload_attachment_success(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, user_id=1, target_date=date(2023, 10, 1))
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.get", return_value=request)
    mocker.patch("app.services.payroll_service.payroll_service.validate_period_open")
    
    file_content = b"%PDF-1.4..."
    file = UploadFile(filename="test.pdf", file=BytesIO(file_content))
    
    mocker.patch("shutil.copyfileobj")
    mocker.patch("builtins.open", mocker.mock_open())
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.create_attachment", return_value="Attachment")
    mocker.patch("app.services.audit_service.audit_service.log")
    
    res = adjustment_service.upload_attachment(db_session_mock, 1, file, 1)
    assert res == "Attachment"

def test_approve_adjustment_not_found(db_session_mock, mocker):
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.get", return_value=None)
    with pytest.raises(HTTPException) as exc:
        adjustment_service.approve_adjustment(db_session_mock, 1, 99)
    assert exc.value.status_code == 404

def test_reject_adjustment_not_found(db_session_mock, mocker):
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.get", return_value=None)
    with pytest.raises(HTTPException) as exc:
        adjustment_service.reject_adjustment(db_session_mock, 1, 99, "comentario")
    assert exc.value.status_code == 404

def test_revert_adjustment_action_waiver(db_session_mock):
    request = AdjustmentRequest(id=1, adjustment_type=AdjustmentType.WAIVER)
    adjustment_service._revert_adjustment_action(db_session_mock, request, 99)

def test_revert_adjustment_action_delete_punch(db_session_mock, mocker):
    request = AdjustmentRequest(user_id=1, target_date=date(2023, 10, 1), time=time(8, 0), adjustment_type=AdjustmentType.DELETE_PUNCH, record_type=RecordType.ENTRY)
    record = TimeRecord(id=1)
    db_session_mock.query.return_value.items = [record]
    
    adjustment_service._revert_adjustment_action(db_session_mock, request, 99)
    assert record.is_ignored is False
    assert record.deleted_at is None

def test_revert_adjustment_status_not_found(db_session_mock, mocker):
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.get", return_value=None)
    with pytest.raises(HTTPException) as exc:
        adjustment_service.revert_adjustment_status(db_session_mock, 1, 99, AdjustmentStatus.PENDING, "motivo")
    assert exc.value.status_code == 404

def test_revert_adjustment_status_same(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, target_date=date(2023, 10, 1), status=AdjustmentStatus.PENDING)
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.get", return_value=request)
    mocker.patch("app.services.payroll_service.payroll_service.validate_period_open")
    mocker.patch("app.services.adjustment_service.AdjustmentService._enrich_adjustments_with_records", return_value=[request])
    
    res = adjustment_service.revert_adjustment_status(db_session_mock, 1, 99, AdjustmentStatus.PENDING, "motivo")
    assert res.status == AdjustmentStatus.PENDING

def test_revert_adjustment_status_approve(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, target_date=date(2023, 10, 1), status=AdjustmentStatus.PENDING, adjustment_type=AdjustmentType.FORGOT_PUNCH)
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.get", return_value=request)
    mocker.patch("app.services.payroll_service.payroll_service.validate_period_open")
    mocker.patch("app.services.adjustment_service.AdjustmentService._execute_adjustment_action")
    mocker.patch("app.repositories.adjustment_repository.adjustment_repository.update_status", return_value=AdjustmentRequest(id=1, status=AdjustmentStatus.APPROVED))
    mocker.patch("app.services.audit_service.audit_service.compute_diffs", return_value=({"status": "PENDING"}, {"status": "APPROVED"}))
    mocker.patch("app.services.audit_service.audit_service.log")
    mocker.patch("app.services.adjustment_service.AdjustmentService._enrich_adjustments_with_records", return_value=[AdjustmentRequest(id=1, status=AdjustmentStatus.APPROVED)])
    
    res = adjustment_service.revert_adjustment_status(db_session_mock, 1, 99, AdjustmentStatus.APPROVED, "motivo")
    assert res.status == AdjustmentStatus.APPROVED

