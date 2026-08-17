from datetime import date, datetime, time
from io import BytesIO

from fastapi import HTTPException, UploadFile

import pytest
from app.features.adjustments.adjustment_models import AdjustmentAttachment, AdjustmentRequest
from app.features.adjustments.adjustment_schemas import AdjustmentRequestCreate, AdjustmentWaiverCreate, \
    BulkReprocessExtraTimeRequest
from app.features.adjustments.adjustment_service import adjustment_service
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import User
from app.shared.enums import AdjustmentStatus, AdjustmentType, RecordType, UserRole


def test_execute_and_revert_action_no_time(db_session_mock):
    req = AdjustmentRequest(user_id=1, target_date=date(2026, 1, 1), time=None)
    adjustment_service._execute_adjustment_action(db_session_mock, req, 1)
    adjustment_service._revert_adjustment_action(db_session_mock, req, 1)


def test_cancel_adjustment_not_found(db_session_mock, mocker):
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get", return_value=None)
    with pytest.raises(HTTPException) as exc1:
        adjustment_service.cancel_adjustment(db_session_mock, 999, 1)
    assert exc1.value.status_code == 404


def test_cancel_adjustment_forbidden_other_user(db_session_mock, mocker):
    target = date(2026, 1, 1)
    req_other = AdjustmentRequest(id=1, user_id=2, status=AdjustmentStatus.PENDING, target_date=target)
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get", return_value=req_other)
    with pytest.raises(HTTPException) as exc2:
        adjustment_service.cancel_adjustment(db_session_mock, 1, 1)
    assert exc2.value.status_code == 403


def test_cancel_adjustment_invalid_status_approved(db_session_mock, mocker):
    target = date(2026, 1, 1)
    req_approved = AdjustmentRequest(id=1, user_id=1, status=AdjustmentStatus.APPROVED, target_date=target)
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get", return_value=req_approved)
    with pytest.raises(HTTPException) as exc3:
        adjustment_service.cancel_adjustment(db_session_mock, 1, 1)
    assert exc3.value.status_code == 400


def test_cancel_adjustment_pending_attribute_error(db_session_mock, mocker):
    target = date(2026, 1, 1)
    req_pending = AdjustmentRequest(id=1, user_id=1, status=AdjustmentStatus.PENDING, target_date=target)
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get", return_value=req_pending)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.validate_period_open")
    with pytest.raises(AttributeError):
        adjustment_service.cancel_adjustment(db_session_mock, 1, 1)


def test_get_attachment_file_path_not_found(db_session_mock, mocker):
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get", return_value=None)
    emp = User(id=1, role=UserRole.EMPLOYEE)
    with pytest.raises(HTTPException) as exc1:
        adjustment_service.get_attachment_file_path(db_session_mock, 999, emp)
    assert exc1.value.status_code == 404


def test_get_attachment_file_path_forbidden(db_session_mock, mocker):
    emp = User(id=1, role=UserRole.EMPLOYEE)
    req = AdjustmentRequest(id=1, user_id=2, attachments=[])
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get", return_value=req)
    with pytest.raises(HTTPException) as exc2:
        adjustment_service.get_attachment_file_path(db_session_mock, 1, emp)
    assert exc2.value.status_code == 403


def test_get_attachment_file_path_no_attachments(db_session_mock, mocker):
    emp = User(id=1, role=UserRole.EMPLOYEE)
    req_own = AdjustmentRequest(id=1, user_id=1, attachments=[])
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get", return_value=req_own)
    with pytest.raises(HTTPException) as exc3:
        adjustment_service.get_attachment_file_path(db_session_mock, 1, emp)
    assert exc3.value.status_code == 404


def test_get_attachment_file_path_file_not_found(db_session_mock, mocker):
    emp = User(id=1, role=UserRole.EMPLOYEE)
    att = AdjustmentAttachment(id=1, file_path="/non_existent/path/doc.pdf")
    req_att = AdjustmentRequest(id=1, user_id=1, attachments=[att])
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get", return_value=req_att)
    with pytest.raises(HTTPException) as exc4:
        adjustment_service.get_attachment_file_path(db_session_mock, 1, emp)
    assert exc4.value.status_code == 404


def test_get_attachment_file_path_fallback_success(db_session_mock, mocker):
    emp = User(id=1, role=UserRole.EMPLOYEE)
    att = AdjustmentAttachment(id=1, file_path="/non_existent/path/doc.pdf")
    req_att = AdjustmentRequest(id=1, user_id=1, attachments=[att])
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get", return_value=req_att)
    mocker.patch("os.path.exists", side_effect=[False, True])
    path, fname = adjustment_service.get_attachment_file_path(db_session_mock, 1, emp)
    assert path == "/non_existent/path/doc.pdf"
    assert fname == "doc.pdf"


def test_reprocess_historical_extra_time_scenarios(db_session_mock, mocker):
    emp = User(id=1, role=UserRole.EMPLOYEE)
    req_in = BulkReprocessExtraTimeRequest(start_date=date(2025, 12, 1), end_date=date(2026, 1, 1), user_ids=[1])
    with pytest.raises(HTTPException) as exc1:
        adjustment_service.reprocess_historical_extra_time(db_session_mock, req_in, emp)
    assert exc1.value.status_code == 403

    maint = User(id=1, role=UserRole.MAINTAINER)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.validate_period_open")
    mocker.patch("app.shared.tolerance_cron_service.tolerance_cron_service.reprocess_historical_entries")
    mocker.patch("app.features.system.audit_service.audit_service.log_change")

    res = adjustment_service.reprocess_historical_extra_time(db_session_mock, req_in, maint)
    assert res["status"] == "success"


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
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get_waivers_by_user_and_date",
                 return_value=[AdjustmentRequest(amount_hours=2.0)])
    adjustment_service._validate_waiver_limit(db_session_mock, 1, date(2023, 10, 1), 5.0)


def test_validate_waiver_limit_exceeded(db_session_mock, mocker):
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get_waivers_by_user_and_date",
                 return_value=[AdjustmentRequest(amount_hours=8.0)])
    target_date = date(2023, 10, 1)
    with pytest.raises(HTTPException) as exc:
        adjustment_service._validate_waiver_limit(db_session_mock, 1, target_date, 5.0)
    assert exc.value.status_code == 400


def test_create_adjustment_request(db_session_mock, mocker):
    mocker.patch("app.features.payroll.payroll_service.payroll_service.validate_period_open")
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._validate_waiver_limit")
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.create",
                 return_value=AdjustmentRequest(id=1, user_id=1, target_date=date(2023, 10, 1)))
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._enrich_adjustments_with_records",
                 return_value=[AdjustmentRequest(id=1)])

    obj_in = AdjustmentRequestCreate(adjustment_type=AdjustmentType.WAIVER, target_date=date(2023, 10, 1),
                                     amount_hours=2.0, reason_text="teste")
    res = adjustment_service.create_adjustment_request(db_session_mock, 1, obj_in)
    assert res.id == 1


def test_create_manager_waiver(db_session_mock, mocker):
    mocker.patch("app.features.payroll.payroll_service.payroll_service.validate_period_open")
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._validate_waiver_limit")
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.create")
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.update_status",
                 return_value=AdjustmentRequest(id=1, user_id=1, target_date=date(2023, 10, 1)))
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._enrich_adjustments_with_records",
                 return_value=[AdjustmentRequest(id=1)])
    mocker.patch("app.features.system.audit_service.audit_service.log_change")

    obj_in = AdjustmentWaiverCreate(user_id=1, target_date=date(2023, 10, 1), amount_hours=8.0, reason_text="teste")
    res = adjustment_service.create_manager_waiver(db_session_mock, obj_in, 99)
    assert res.id == 1


def test_admin_delete_adjustment(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, adjustment_type=AdjustmentType.EXTRA_TIME, target_date=date(2023, 10, 1),
                                status=AdjustmentStatus.APPROVED)
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get", return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.validate_period_open")
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._revert_adjustment_action")
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.soft_delete")
    mocker.patch("app.features.system.audit_service.audit_service.log_change")

    adjustment_service.admin_delete_adjustment(db_session_mock, 1, 99, "Justificativa teste")


def test_delete_adjustment_not_found(db_session_mock, mocker):
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get", return_value=None)
    with pytest.raises(HTTPException) as exc:
        adjustment_service.delete_adjustment(db_session_mock, 1, 99, "Justificativa teste")
    assert exc.value.status_code == 404


def test_approve_adjustment(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, target_date=date(2023, 10, 1), adjustment_type=AdjustmentType.FORGOT_PUNCH,
                                status=AdjustmentStatus.PENDING)
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get", return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.validate_period_open")
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._execute_adjustment_action")
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.update_status",
                 return_value=AdjustmentRequest(id=1, status=AdjustmentStatus.APPROVED))
    mocker.patch("app.features.system.audit_service.audit_service.compute_diffs",
                 return_value=({"status": "PENDING"}, {"status": "APPROVED"}))
    mocker.patch("app.features.system.audit_service.audit_service.log_change")
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._enrich_adjustments_with_records",
                 return_value=[AdjustmentRequest(id=1, status=AdjustmentStatus.APPROVED)])

    res = adjustment_service.approve_adjustment(db_session_mock, 1, 99)
    assert res.status == AdjustmentStatus.APPROVED


def test_approve_adjustment_waiver_no_attachment(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, target_date=date(2023, 10, 1), adjustment_type=AdjustmentType.WAIVER,
                                attachments=[])
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get", return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.validate_period_open")
    with pytest.raises(HTTPException) as exc:
        adjustment_service.approve_adjustment(db_session_mock, 1, 99)
    assert exc.value.status_code == 400


def test_reject_adjustment(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, target_date=date(2023, 10, 1), status=AdjustmentStatus.PENDING)
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get", return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.validate_period_open")
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.update_status",
                 return_value=AdjustmentRequest(id=1, status=AdjustmentStatus.REJECTED))
    mocker.patch("app.features.system.audit_service.audit_service.compute_diffs",
                 return_value=({"status": "PENDING"}, {"status": "REJECTED"}))
    mocker.patch("app.features.system.audit_service.audit_service.log_change")
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._enrich_adjustments_with_records",
                 return_value=[AdjustmentRequest(id=1, status=AdjustmentStatus.REJECTED)])

    res = adjustment_service.reject_adjustment(db_session_mock, 1, 99, "comentario")
    assert res.status == AdjustmentStatus.REJECTED

    request_approved = AdjustmentRequest(id=2, target_date=date(2023, 10, 1), status=AdjustmentStatus.APPROVED,
                                         adjustment_type=AdjustmentType.WAIVER)
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get",
                 return_value=request_approved)
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._revert_adjustment_action")
    res_approved = adjustment_service.reject_adjustment(db_session_mock, 2, 99, None)
    assert res_approved.status == AdjustmentStatus.REJECTED


def test_execute_adjustment_action_create(db_session_mock, mocker):
    request = AdjustmentRequest(user_id=1, target_date=date(2023, 10, 1), time=time(8, 0),
                                adjustment_type=AdjustmentType.FORGOT_PUNCH, record_type=RecordType.ENTRY)
    mocker.patch("app.features.time_records.time_record_repository.time_record_repository.create")
    adjustment_service._execute_adjustment_action(db_session_mock, request, 99)


def test_execute_adjustment_action_delete(db_session_mock, mocker):
    request = AdjustmentRequest(user_id=1, target_date=date(2023, 10, 1), time=time(8, 0),
                                adjustment_type=AdjustmentType.DELETE_PUNCH, record_type=RecordType.ENTRY)
    record = TimeRecord(id=1)
    db_session_mock.query.return_value.items = [record]
    mocker.patch("app.features.time_records.time_record_repository.get_local_time")

    adjustment_service._execute_adjustment_action(db_session_mock, request, 99)
    assert record.is_ignored is True


def test_revert_adjustment_action(db_session_mock, mocker):
    request = AdjustmentRequest(user_id=1, target_date=date(2023, 10, 1), time=time(8, 0),
                                adjustment_type=AdjustmentType.FORGOT_PUNCH, record_type=RecordType.ENTRY)
    record = TimeRecord(id=1)
    db_session_mock.query.return_value.items = [record]
    mocker.patch("app.features.time_records.time_record_repository.get_local_time")

    adjustment_service._revert_adjustment_action(db_session_mock, request, 99)
    assert record.is_ignored is True


def test_revert_adjustment_status(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, target_date=date(2023, 10, 1), status=AdjustmentStatus.APPROVED,
                                adjustment_type=AdjustmentType.FORGOT_PUNCH)
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get", return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.validate_period_open")
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._revert_adjustment_action")
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.update_status",
                 return_value=AdjustmentRequest(id=1, status=AdjustmentStatus.PENDING))
    mocker.patch("app.features.system.audit_service.audit_service.compute_diffs",
                 return_value=({"status": "APPROVED"}, {"status": "PENDING"}))
    mocker.patch("app.features.system.audit_service.audit_service.log_change")
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._enrich_adjustments_with_records",
                 return_value=[AdjustmentRequest(id=1, status=AdjustmentStatus.PENDING)])

    res = adjustment_service.revert_adjustment_status(db_session_mock, 1, 99, AdjustmentStatus.PENDING, "motivo")
    assert res.status == AdjustmentStatus.PENDING


def test_enrich_adjustments_with_records_empty(db_session_mock):
    res = adjustment_service._enrich_adjustments_with_records(db_session_mock, [])
    assert res == []


def test_validate_waiver_limit_no_amount(db_session_mock):
    adjustment_service._validate_waiver_limit(db_session_mock, 1, date(2023, 10, 1), None)


def test_get_all_enriched(db_session_mock, mocker):
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get_all", return_value=[])
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._enrich_adjustments_with_records",
                 return_value=[])
    assert adjustment_service.get_all_enriched(db_session_mock) == []


def test_get_my_enriched(db_session_mock, mocker):
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get_all_by_user",
                 return_value=[])
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._enrich_adjustments_with_records",
                 return_value=[])
    assert adjustment_service.get_my_enriched(db_session_mock, 1) == []


def test_admin_delete_adjustment_not_found(db_session_mock, mocker):
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get", return_value=None)
    with pytest.raises(HTTPException) as exc:
        adjustment_service.admin_delete_adjustment(db_session_mock, 1, 99, "Justificativa teste")
    assert exc.value.status_code == 404


def test_delete_adjustment_success(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, adjustment_type=AdjustmentType.EXTRA_TIME, target_date=date(2023, 10, 1),
                                status=AdjustmentStatus.APPROVED)
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get", return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.validate_period_open")
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._revert_adjustment_action")
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.soft_delete")
    mocker.patch("app.features.system.audit_service.audit_service.log_change")

    adjustment_service.delete_adjustment(db_session_mock, 1, 99, "Justificativa teste")


def test_delete_extra_time_adjustment_success(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, adjustment_type=AdjustmentType.EXTRA_TIME, target_date=date(2023, 10, 1),
                                status=AdjustmentStatus.APPROVED)
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get", return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.validate_period_open")
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._revert_adjustment_action")
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.soft_delete")
    mock_audit_log = mocker.patch("app.features.system.audit_service.audit_service.log_change")

    adjustment_service.delete_adjustment(db_session_mock, 1, 99, "Justificativa exclusao hora extra")
    mock_audit_log.assert_called_once()
    assert mock_audit_log.call_args[0][2] == "DELETE_ADJUSTMENT"
    assert mock_audit_log.call_args[1]["new_data"] == {"reason": "Justificativa exclusao hora extra"}


def test_delete_waiver_adjustment_success(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, adjustment_type=AdjustmentType.WAIVER, target_date=date(2023, 10, 1),
                                status=AdjustmentStatus.APPROVED)
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get", return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.validate_period_open")
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._revert_adjustment_action")
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.soft_delete")
    mock_audit_log = mocker.patch("app.features.system.audit_service.audit_service.log_change")

    adjustment_service.delete_adjustment(db_session_mock, 1, 99, "Justificativa exclusao abono")
    mock_audit_log.assert_called_once()
    assert mock_audit_log.call_args[0][2] == "DELETE_ADJUSTMENT"
    assert mock_audit_log.call_args[1]["new_data"] == {"reason": "Justificativa exclusao abono"}


def test_delete_adjustment_wrong_type_blocked(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, adjustment_type=AdjustmentType.PUNCH_NOT_COUNTED, target_date=date(2023, 10, 1),
                                status=AdjustmentStatus.APPROVED)
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get", return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.validate_period_open")
    mock_soft_delete = mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.soft_delete")

    with pytest.raises(HTTPException) as exc:
        adjustment_service.delete_adjustment(db_session_mock, 1, 99, "Justificativa teste")
    assert exc.value.status_code == 400
    assert "WAIVER" in exc.value.detail
    mock_soft_delete.assert_not_called()


def test_admin_delete_adjustment_wrong_type_blocked(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, adjustment_type=AdjustmentType.FORGOT_PUNCH, target_date=date(2023, 10, 1),
                                status=AdjustmentStatus.APPROVED)
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get", return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.validate_period_open")
    mock_soft_delete = mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.soft_delete")

    with pytest.raises(HTTPException) as exc:
        adjustment_service.admin_delete_adjustment(db_session_mock, 1, 99, "Justificativa teste")
    assert exc.value.status_code == 400
    assert "WAIVER" in exc.value.detail
    mock_soft_delete.assert_not_called()


def test_upload_attachment_not_found(db_session_mock, mocker):
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get", return_value=None)
    upload_file = UploadFile(filename="test.png", file=BytesIO(b""))
    with pytest.raises(HTTPException) as exc:
        adjustment_service.upload_attachment(db_session_mock, 1, upload_file, 1)
    assert exc.value.status_code == 404


def test_upload_attachment_forbidden(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, user_id=2)
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get", return_value=request)
    upload_file = UploadFile(filename="test.png", file=BytesIO(b""))
    with pytest.raises(HTTPException) as exc:
        adjustment_service.upload_attachment(db_session_mock, 1, upload_file, 1)
    assert exc.value.status_code == 403


def test_upload_attachment_invalid_name(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, user_id=1, target_date=date(2023, 10, 1))
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get", return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.validate_period_open")
    upload_file = UploadFile(filename="test", file=BytesIO(b""))
    with pytest.raises(HTTPException) as exc:
        adjustment_service.upload_attachment(db_session_mock, 1, upload_file, 1)
    assert exc.value.status_code == 400


def test_upload_attachment_invalid_ext(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, user_id=1, target_date=date(2023, 10, 1))
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get", return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.validate_period_open")
    upload_file = UploadFile(filename="test.txt", file=BytesIO(b""))
    with pytest.raises(HTTPException) as exc:
        adjustment_service.upload_attachment(db_session_mock, 1, upload_file, 1)
    assert exc.value.status_code == 400


def test_upload_attachment_invalid_content(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, user_id=1, target_date=date(2023, 10, 1))
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get", return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.validate_period_open")
    upload_file = UploadFile(filename="test.png", file=BytesIO(b"invalid"))
    with pytest.raises(HTTPException) as exc:
        adjustment_service.upload_attachment(db_session_mock, 1, upload_file, 1)
    assert exc.value.status_code == 400


def test_upload_attachment_success(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, user_id=1, target_date=date(2023, 10, 1))
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get", return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.validate_period_open")

    file_content = b"%PDF-1.4..."
    file = UploadFile(filename="test.pdf", file=BytesIO(file_content))

    mocker.patch("shutil.copyfileobj")
    mocker.patch("builtins.open", mocker.mock_open())
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.create_attachment",
                 return_value="Attachment")
    mocker.patch("app.features.system.audit_service.audit_service.log_change")

    res = adjustment_service.upload_attachment(db_session_mock, 1, file, 1)
    assert res == "Attachment"


def test_approve_adjustment_not_found(db_session_mock, mocker):
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get", return_value=None)
    with pytest.raises(HTTPException) as exc:
        adjustment_service.approve_adjustment(db_session_mock, 1, 99)
    assert exc.value.status_code == 404


def test_reject_adjustment_not_found(db_session_mock, mocker):
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get", return_value=None)
    with pytest.raises(HTTPException) as exc:
        adjustment_service.reject_adjustment(db_session_mock, 1, 99, "comentario")
    assert exc.value.status_code == 404


def test_revert_adjustment_action_waiver(db_session_mock):
    request = AdjustmentRequest(id=1, adjustment_type=AdjustmentType.WAIVER)
    adjustment_service._revert_adjustment_action(db_session_mock, request, 99)


def test_revert_adjustment_action_delete_punch(db_session_mock, mocker):
    request = AdjustmentRequest(user_id=1, target_date=date(2023, 10, 1), time=time(8, 0),
                                adjustment_type=AdjustmentType.DELETE_PUNCH, record_type=RecordType.ENTRY)
    record = TimeRecord(id=1)
    db_session_mock.query.return_value.items = [record]

    adjustment_service._revert_adjustment_action(db_session_mock, request, 99)
    assert record.is_ignored is False
    assert record.deleted_at is None


def test_revert_adjustment_status_not_found(db_session_mock, mocker):
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get", return_value=None)
    with pytest.raises(HTTPException) as exc:
        adjustment_service.revert_adjustment_status(db_session_mock, 1, 99, AdjustmentStatus.PENDING, "motivo")
    assert exc.value.status_code == 404


def test_revert_adjustment_status_same(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, target_date=date(2023, 10, 1), status=AdjustmentStatus.PENDING)
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get", return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.validate_period_open")
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._enrich_adjustments_with_records",
                 return_value=[request])

    res = adjustment_service.revert_adjustment_status(db_session_mock, 1, 99, AdjustmentStatus.PENDING, "motivo")
    assert res.status == AdjustmentStatus.PENDING


def test_revert_adjustment_status_approve(db_session_mock, mocker):
    request = AdjustmentRequest(id=1, target_date=date(2023, 10, 1), status=AdjustmentStatus.PENDING,
                                adjustment_type=AdjustmentType.FORGOT_PUNCH)
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.get", return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.validate_period_open")
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._execute_adjustment_action")
    mocker.patch("app.features.adjustments.adjustment_repository.adjustment_repository.update_status",
                 return_value=AdjustmentRequest(id=1, status=AdjustmentStatus.APPROVED))
    mocker.patch("app.features.system.audit_service.audit_service.compute_diffs",
                 return_value=({"status": "PENDING"}, {"status": "APPROVED"}))
    mocker.patch("app.features.system.audit_service.audit_service.log_change")
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._enrich_adjustments_with_records",
                 return_value=[AdjustmentRequest(id=1, status=AdjustmentStatus.APPROVED)])

    res = adjustment_service.revert_adjustment_status(db_session_mock, 1, 99, AdjustmentStatus.APPROVED, "motivo")
    assert res.status == AdjustmentStatus.APPROVED
