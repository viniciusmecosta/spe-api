from datetime import date, datetime, time
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock

from fastapi import HTTPException, UploadFile

import pytest
from app.features.adjustments.adjustment_exceptions import (
    AdjustmentAttachmentNotFoundError,
    AdjustmentNotFoundError,
    AdjustmentPermissionError,
    AttachmentFileNotFoundError,
    CorruptedAttachmentError,
    InvalidAdjustmentFilenameError,
    InvalidAdjustmentTypeError,
    InvalidAttachmentFormatError,
    WaiverAttachmentRequiredError,
    WaiverLimitExceededError,
)
from app.features.adjustments.adjustment_models import AdjustmentAttachment, AdjustmentRequest
from app.features.adjustments.adjustment_schemas import (
    AdjustmentRequestCreate,
    AdjustmentWaiverCreate,
    BulkReprocessDailyExcessRequest,
)
from app.features.adjustments.adjustment_service import adjustment_service
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import User
from app.shared.enums import AdjustmentStatus, AdjustmentType, RecordType, UserRole


@pytest.mark.asyncio
async def test_execute_and_revert_action_no_time(async_db_mock):
    req = AdjustmentRequest(user_id=1, target_date=date(2026, 1, 1), time=None)
    await adjustment_service._execute_adjustment_action(async_db_mock, req, 1)
    await adjustment_service._revert_adjustment_action(async_db_mock, req, 1)


@pytest.mark.asyncio
async def test_get_attachment_file_path_not_found(async_db_mock, mocker):
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get", new_callable=AsyncMock,
                 return_value=None)
    emp = User(id=1, role=UserRole.EMPLOYEE)
    with pytest.raises(AdjustmentNotFoundError) as exc1:
        await adjustment_service.get_attachment_file_path(async_db_mock, 999, emp)
    assert exc1.value.status_code == 404


@pytest.mark.asyncio
async def test_get_attachment_file_path_forbidden(async_db_mock, mocker):
    emp = User(id=1, role=UserRole.EMPLOYEE)
    req = AdjustmentRequest(id=1, user_id=2, attachments=[])
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get", new_callable=AsyncMock,
                 return_value=req)
    with pytest.raises(AdjustmentPermissionError) as exc2:
        await adjustment_service.get_attachment_file_path(async_db_mock, 1, emp)
    assert exc2.value.status_code == 403


@pytest.mark.asyncio
async def test_get_attachment_file_path_no_attachments(async_db_mock, mocker):
    emp = User(id=1, role=UserRole.EMPLOYEE)
    req_own = AdjustmentRequest(id=1, user_id=1, attachments=[])
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get", new_callable=AsyncMock,
                 return_value=req_own)
    with pytest.raises(AdjustmentAttachmentNotFoundError) as exc3:
        await adjustment_service.get_attachment_file_path(async_db_mock, 1, emp)
    assert exc3.value.status_code == 404


@pytest.mark.asyncio
async def test_get_attachment_file_path_file_not_found(async_db_mock, mocker):
    emp = User(id=1, role=UserRole.EMPLOYEE)
    att = AdjustmentAttachment(id=1, file_path="/non_existent/path/doc.pdf")
    req_att = AdjustmentRequest(id=1, user_id=1, attachments=[att])
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get", new_callable=AsyncMock,
                 return_value=req_att)
    with pytest.raises(AttachmentFileNotFoundError) as exc4:
        await adjustment_service.get_attachment_file_path(async_db_mock, 1, emp)
    assert exc4.value.status_code == 404


@pytest.mark.asyncio
async def test_get_attachment_file_path_fallback_success(async_db_mock, mocker):
    emp = User(id=1, role=UserRole.EMPLOYEE)
    att = AdjustmentAttachment(id=1, file_path="/non_existent/path/doc.pdf")
    req_att = AdjustmentRequest(id=1, user_id=1, attachments=[att])
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get", new_callable=AsyncMock,
                 return_value=req_att)
    mocker.patch("os.path.exists", side_effect=[False, True])
    path, fname = await adjustment_service.get_attachment_file_path(async_db_mock, 1, emp)
    assert path == "/non_existent/path/doc.pdf"
    assert fname == "doc.pdf"


@pytest.mark.asyncio
async def test_reprocess_historical_daily_excess_scenarios(async_db_mock, mocker):
    emp = User(id=1, role=UserRole.EMPLOYEE)
    req_in = BulkReprocessDailyExcessRequest(
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 14),
        user_ids=[1],
        overwrite_reviewed=True,
    )
    bg_mock = MagicMock()

    with pytest.raises(AdjustmentPermissionError) as exc1:
        await adjustment_service.reprocess_historical_daily_excess(
            async_db_mock, req_in, bg_mock, emp
        )
    assert exc1.value.status_code == 403

    maint = User(id=1, role=UserRole.MAINTAINER)

    invalid_req = BulkReprocessDailyExcessRequest(
        start_date=date(2026, 8, 15),
        end_date=date(2026, 8, 1),
        user_ids=[1],
    )
    with pytest.raises(HTTPException) as exc_date:
        await adjustment_service.reprocess_historical_daily_excess(
            async_db_mock, invalid_req, bg_mock, maint
        )
    assert "data inicial não pode ser maior" in str(exc_date.value)

    mocker.patch(
        "app.features.adjustments.adjustment_service.adjustment_service._validate_period_open",
        new_callable=AsyncMock,
    )
    mocker.patch(
        "app.features.system.audit_service.audit_service.async_log_change",
        new_callable=AsyncMock,
    )

    res = await adjustment_service.reprocess_historical_daily_excess(
        async_db_mock, req_in, bg_mock, maint
    )
    assert res["status"] == "success"
    bg_mock.add_task.assert_called_once()


@pytest.mark.asyncio
async def test_enrich_adjustments_with_records(async_db_mock):
    adj1 = AdjustmentRequest(id=1, user_id=1, target_date=date(2023, 10, 1))
    adj2 = AdjustmentRequest(id=2, user_id=1, target_date=date(2023, 10, 2))

    tr1 = TimeRecord(user_id=1, record_datetime=datetime(2023, 10, 1, 8, 0))
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [tr1]
    async_db_mock.scalars.return_value = mock_scalars

    res = await adjustment_service._enrich_adjustments_with_records(async_db_mock, [adj1, adj2])
    assert len(res) == 2
    assert len(res[0].time_records) == 1
    assert len(res[1].time_records) == 0


@pytest.mark.asyncio
async def test_validate_waiver_limit_ok(async_db_mock, mocker):
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get_waivers_by_user_and_date",
                 new_callable=AsyncMock,
                 return_value=[AdjustmentRequest(amount_hours=2.0)])
    await adjustment_service._validate_waiver_limit(async_db_mock, 1, date(2023, 10, 1), 5.0)


@pytest.mark.asyncio
async def test_validate_waiver_limit_exceeded(async_db_mock, mocker):
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get_waivers_by_user_and_date",
                 new_callable=AsyncMock,
                 return_value=[AdjustmentRequest(amount_hours=8.0)])
    target_date = date(2023, 10, 1)
    with pytest.raises(WaiverLimitExceededError) as exc:
        await adjustment_service._validate_waiver_limit(async_db_mock, 1, target_date, 5.0)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_create_adjustment_request(async_db_mock, mocker):
    mocker.patch("app.features.payroll.payroll_service.payroll_service.async_validate_period_open",
                 new_callable=AsyncMock)
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._validate_waiver_limit",
                 new_callable=AsyncMock)
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.create",
                 new_callable=AsyncMock,
                 return_value=AdjustmentRequest(id=1, user_id=1, target_date=date(2023, 10, 1)))
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._enrich_adjustments_with_records",
                 new_callable=AsyncMock,
                 return_value=[AdjustmentRequest(id=1)])

    obj_in = AdjustmentRequestCreate(adjustment_type=AdjustmentType.WAIVER, target_date=date(2023, 10, 1),
                                     amount_hours=2.0, reason_text="teste")
    res = await adjustment_service.create_adjustment_request(async_db_mock, 1, obj_in)
    assert res.id == 1


@pytest.mark.asyncio
async def test_create_manager_waiver(async_db_mock, mocker):
    mocker.patch("app.features.payroll.payroll_service.payroll_service.async_validate_period_open",
                 new_callable=AsyncMock)
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._validate_waiver_limit",
                 new_callable=AsyncMock)
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.create",
                 new_callable=AsyncMock)
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.update_status",
                 new_callable=AsyncMock,
                 return_value=AdjustmentRequest(id=1, user_id=1, target_date=date(2023, 10, 1)))
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._enrich_adjustments_with_records",
                 new_callable=AsyncMock,
                 return_value=[AdjustmentRequest(id=1)])
    mocker.patch("app.features.system.audit_service.audit_service.async_log_change", new_callable=AsyncMock)
    mock_eval = mocker.patch("app.features.adjustments.adjustment_service.daily_excess_service.evaluate_user_day_async", new_callable=AsyncMock)

    obj_in = AdjustmentWaiverCreate(user_id=1, target_date=date(2023, 10, 1), amount_hours=8.0, reason_text="teste")
    res = await adjustment_service.create_manager_waiver(async_db_mock, obj_in, 99)
    assert res.id == 1
    mock_eval.assert_awaited_once_with(async_db_mock, 1, date(2023, 10, 1))


@pytest.mark.asyncio
async def test_admin_delete_adjustment(async_db_mock, mocker):
    request = AdjustmentRequest(id=1, adjustment_type=AdjustmentType.EXTRA_TIME, target_date=date(2023, 10, 1),
                                status=AdjustmentStatus.APPROVED)
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get", new_callable=AsyncMock,
                 return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.async_validate_period_open",
                 new_callable=AsyncMock)
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._revert_adjustment_action",
                 new_callable=AsyncMock)
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.soft_delete",
                 new_callable=AsyncMock)
    mocker.patch("app.features.system.audit_service.audit_service.async_log_change", new_callable=AsyncMock)

    await adjustment_service.admin_delete_adjustment(async_db_mock, 1, 99, "Justificativa teste")


@pytest.mark.asyncio
async def test_delete_adjustment_not_found(async_db_mock, mocker):
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get", new_callable=AsyncMock,
                 return_value=None)
    with pytest.raises(AdjustmentNotFoundError) as exc:
        await adjustment_service.delete_adjustment(async_db_mock, 1, 99, "Justificativa teste")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_approve_adjustment(async_db_mock, mocker):
    request = AdjustmentRequest(id=1, user_id=1, target_date=date(2023, 10, 1), adjustment_type=AdjustmentType.FORGOT_PUNCH,
                                status=AdjustmentStatus.PENDING)
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get", new_callable=AsyncMock,
                 return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.async_validate_period_open",
                 new_callable=AsyncMock)
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._execute_adjustment_action",
                 new_callable=AsyncMock)
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.update_status",
                 new_callable=AsyncMock,
                 return_value=AdjustmentRequest(id=1, status=AdjustmentStatus.APPROVED))
    mocker.patch("app.features.system.audit_service.audit_service.async_log_change", new_callable=AsyncMock)
    mock_eval = mocker.patch("app.features.adjustments.adjustment_service.daily_excess_service.evaluate_user_day_async", new_callable=AsyncMock)
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._enrich_adjustments_with_records",
                 new_callable=AsyncMock,
                 return_value=[AdjustmentRequest(id=1, status=AdjustmentStatus.APPROVED)])

    res = await adjustment_service.approve_adjustment(async_db_mock, 1, 99)
    assert res.status == AdjustmentStatus.APPROVED
    mock_eval.assert_awaited_once_with(async_db_mock, 1, date(2023, 10, 1))


@pytest.mark.asyncio
async def test_approve_adjustment_waiver_no_attachment(async_db_mock, mocker):
    request = AdjustmentRequest(id=1, target_date=date(2023, 10, 1), adjustment_type=AdjustmentType.WAIVER,
                                attachments=[])
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get", new_callable=AsyncMock,
                 return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.async_validate_period_open",
                 new_callable=AsyncMock)
    with pytest.raises(WaiverAttachmentRequiredError) as exc:
        await adjustment_service.approve_adjustment(async_db_mock, 1, 99)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_reject_adjustment(async_db_mock, mocker):
    request = AdjustmentRequest(id=1, target_date=date(2023, 10, 1), status=AdjustmentStatus.PENDING)
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get", new_callable=AsyncMock,
                 return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.async_validate_period_open",
                 new_callable=AsyncMock)
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.update_status",
                 new_callable=AsyncMock,
                 return_value=AdjustmentRequest(id=1, status=AdjustmentStatus.REJECTED))
    mocker.patch("app.features.system.audit_service.audit_service.async_log_change", new_callable=AsyncMock)
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._enrich_adjustments_with_records",
                 new_callable=AsyncMock,
                 return_value=[AdjustmentRequest(id=1, status=AdjustmentStatus.REJECTED)])

    res = await adjustment_service.reject_adjustment(async_db_mock, 1, 99, "comentario")
    assert res.status == AdjustmentStatus.REJECTED

    request_approved = AdjustmentRequest(id=2, target_date=date(2023, 10, 1), status=AdjustmentStatus.APPROVED,
                                         adjustment_type=AdjustmentType.WAIVER)
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get",
                 new_callable=AsyncMock,
                 return_value=request_approved)
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._revert_adjustment_action",
                 new_callable=AsyncMock)
    res_approved = await adjustment_service.reject_adjustment(async_db_mock, 2, 99, None)
    assert res_approved.status == AdjustmentStatus.REJECTED


@pytest.mark.asyncio
async def test_execute_adjustment_action_create(async_db_mock, mocker):
    request = AdjustmentRequest(user_id=1, target_date=date(2023, 10, 1), time=time(8, 0),
                                adjustment_type=AdjustmentType.FORGOT_PUNCH, record_type=RecordType.ENTRY)
    await adjustment_service._execute_adjustment_action(async_db_mock, request, 99)
    async_db_mock.add.assert_called_once()


@pytest.mark.asyncio
async def test_execute_adjustment_action_delete(async_db_mock, mocker):
    request = AdjustmentRequest(user_id=1, target_date=date(2023, 10, 1), time=time(8, 0),
                                adjustment_type=AdjustmentType.DELETE_PUNCH, record_type=RecordType.ENTRY)
    record = TimeRecord(id=1)
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = record
    async_db_mock.scalars.return_value = mock_scalars
    mocker.patch("app.features.time_records.time_record_repository.get_local_time")

    await adjustment_service._execute_adjustment_action(async_db_mock, request, 99)
    assert record.is_ignored is True


@pytest.mark.asyncio
async def test_revert_adjustment_action(async_db_mock, mocker):
    request = AdjustmentRequest(user_id=1, target_date=date(2023, 10, 1), time=time(8, 0),
                                adjustment_type=AdjustmentType.FORGOT_PUNCH, record_type=RecordType.ENTRY)
    record = TimeRecord(id=1)
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = record
    async_db_mock.scalars.return_value = mock_scalars
    mocker.patch("app.features.time_records.time_record_repository.get_local_time")

    await adjustment_service._revert_adjustment_action(async_db_mock, request, 99)
    assert record.is_ignored is True


@pytest.mark.asyncio
async def test_revert_adjustment_status(async_db_mock, mocker):
    request = AdjustmentRequest(id=1, target_date=date(2023, 10, 1), status=AdjustmentStatus.APPROVED,
                                adjustment_type=AdjustmentType.FORGOT_PUNCH)
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get", new_callable=AsyncMock,
                 return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.async_validate_period_open",
                 new_callable=AsyncMock)
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._revert_adjustment_action",
                 new_callable=AsyncMock)
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.update_status",
                 new_callable=AsyncMock,
                 return_value=AdjustmentRequest(id=1, status=AdjustmentStatus.PENDING))
    mocker.patch("app.features.system.audit_service.audit_service.async_log_change", new_callable=AsyncMock)
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._enrich_adjustments_with_records",
                 new_callable=AsyncMock,
                 return_value=[AdjustmentRequest(id=1, status=AdjustmentStatus.PENDING)])

    res = await adjustment_service.revert_adjustment_status(async_db_mock, 1, 99, AdjustmentStatus.PENDING, "motivo")
    assert res.status == AdjustmentStatus.PENDING


@pytest.mark.asyncio
async def test_enrich_adjustments_with_records_empty(async_db_mock):
    res = await adjustment_service._enrich_adjustments_with_records(async_db_mock, [])
    assert res == []


@pytest.mark.asyncio
async def test_validate_waiver_limit_no_amount(async_db_mock):
    await adjustment_service._validate_waiver_limit(async_db_mock, 1, date(2023, 10, 1), None)


@pytest.mark.asyncio
async def test_get_all_enriched(async_db_mock, mocker):
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get_all",
                 new_callable=AsyncMock, return_value=[])
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._enrich_adjustments_with_records",
                 new_callable=AsyncMock,
                 return_value=[])
    assert await adjustment_service.get_all_enriched(async_db_mock) == []


@pytest.mark.asyncio
async def test_get_my_enriched(async_db_mock, mocker):
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get_all_by_user",
                 new_callable=AsyncMock,
                 return_value=[])
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._enrich_adjustments_with_records",
                 new_callable=AsyncMock,
                 return_value=[])
    assert await adjustment_service.get_my_enriched(async_db_mock, 1) == []


@pytest.mark.asyncio
async def test_admin_delete_adjustment_not_found(async_db_mock, mocker):
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get", new_callable=AsyncMock,
                 return_value=None)
    with pytest.raises(AdjustmentNotFoundError) as exc:
        await adjustment_service.admin_delete_adjustment(async_db_mock, 1, 99, "Justificativa teste")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_adjustment_success(async_db_mock, mocker):
    request = AdjustmentRequest(id=1, adjustment_type=AdjustmentType.EXTRA_TIME, target_date=date(2023, 10, 1),
                                status=AdjustmentStatus.APPROVED)
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get", new_callable=AsyncMock,
                 return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.async_validate_period_open",
                 new_callable=AsyncMock)
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._revert_adjustment_action",
                 new_callable=AsyncMock)
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.soft_delete",
                 new_callable=AsyncMock)
    mocker.patch("app.features.system.audit_service.audit_service.async_log_change", new_callable=AsyncMock)

    await adjustment_service.delete_adjustment(async_db_mock, 1, 99, "Justificativa teste")


@pytest.mark.asyncio
async def test_delete_extra_time_adjustment_success(async_db_mock, mocker):
    request = AdjustmentRequest(id=1, adjustment_type=AdjustmentType.EXTRA_TIME, target_date=date(2023, 10, 1),
                                status=AdjustmentStatus.APPROVED)
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get", new_callable=AsyncMock,
                 return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.async_validate_period_open",
                 new_callable=AsyncMock)
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._revert_adjustment_action",
                 new_callable=AsyncMock)
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.soft_delete",
                 new_callable=AsyncMock)
    mock_audit_log = mocker.patch("app.features.system.audit_service.audit_service.async_log_change",
                                  new_callable=AsyncMock)

    await adjustment_service.delete_adjustment(async_db_mock, 1, 99, "Justificativa exclusao hora extra")
    mock_audit_log.assert_called_once()
    assert mock_audit_log.call_args[0][2] == "DELETE_ADJUSTMENT"
    assert mock_audit_log.call_args[1]["new_data"] == {"reason": "Justificativa exclusao hora extra"}


@pytest.mark.asyncio
async def test_delete_waiver_adjustment_success(async_db_mock, mocker):
    request = AdjustmentRequest(id=1, adjustment_type=AdjustmentType.WAIVER, target_date=date(2023, 10, 1),
                                status=AdjustmentStatus.APPROVED)
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get", new_callable=AsyncMock,
                 return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.async_validate_period_open",
                 new_callable=AsyncMock)
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._revert_adjustment_action",
                 new_callable=AsyncMock)
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.soft_delete",
                 new_callable=AsyncMock)
    mock_audit_log = mocker.patch("app.features.system.audit_service.audit_service.async_log_change",
                                  new_callable=AsyncMock)

    await adjustment_service.delete_adjustment(async_db_mock, 1, 99, "Justificativa exclusao abono")
    mock_audit_log.assert_called_once()
    assert mock_audit_log.call_args[0][2] == "DELETE_ADJUSTMENT"
    assert mock_audit_log.call_args[1]["new_data"] == {"reason": "Justificativa exclusao abono"}


@pytest.mark.asyncio
async def test_delete_adjustment_wrong_type_blocked(async_db_mock, mocker):
    request = AdjustmentRequest(id=1, adjustment_type=AdjustmentType.PUNCH_NOT_COUNTED, target_date=date(2023, 10, 1),
                                status=AdjustmentStatus.APPROVED)
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get", new_callable=AsyncMock,
                 return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.async_validate_period_open",
                 new_callable=AsyncMock)
    mock_soft_delete = mocker.patch(
        "app.features.adjustments.adjustment_service.async_adjustment_repository.soft_delete", new_callable=AsyncMock)

    with pytest.raises(InvalidAdjustmentTypeError) as exc:
        await adjustment_service.delete_adjustment(async_db_mock, 1, 99, "Justificativa teste")
    assert exc.value.status_code == 400
    assert "WAIVER" in exc.value.detail
    mock_soft_delete.assert_not_called()


@pytest.mark.asyncio
async def test_admin_delete_adjustment_wrong_type_blocked(async_db_mock, mocker):
    request = AdjustmentRequest(id=1, adjustment_type=AdjustmentType.FORGOT_PUNCH, target_date=date(2023, 10, 1),
                                status=AdjustmentStatus.APPROVED)
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get", new_callable=AsyncMock,
                 return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.async_validate_period_open",
                 new_callable=AsyncMock)
    mock_soft_delete = mocker.patch(
        "app.features.adjustments.adjustment_service.async_adjustment_repository.soft_delete", new_callable=AsyncMock)

    with pytest.raises(InvalidAdjustmentTypeError) as exc:
        await adjustment_service.admin_delete_adjustment(async_db_mock, 1, 99, "Justificativa teste")
    assert exc.value.status_code == 400
    assert "WAIVER" in exc.value.detail
    mock_soft_delete.assert_not_called()


@pytest.mark.asyncio
async def test_upload_attachment_not_found(async_db_mock, mocker):
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get", new_callable=AsyncMock,
                 return_value=None)
    upload_file = UploadFile(filename="test.png", file=BytesIO(b""))
    with pytest.raises(AdjustmentNotFoundError) as exc:
        await adjustment_service.upload_attachment(async_db_mock, 1, upload_file, 1)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_upload_attachment_forbidden(async_db_mock, mocker):
    request = AdjustmentRequest(id=1, user_id=2)
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get", new_callable=AsyncMock,
                 return_value=request)
    upload_file = UploadFile(filename="test.png", file=BytesIO(b""))
    with pytest.raises(AdjustmentPermissionError) as exc:
        await adjustment_service.upload_attachment(async_db_mock, 1, upload_file, 1)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_upload_attachment_invalid_name(async_db_mock, mocker):
    request = AdjustmentRequest(id=1, user_id=1, target_date=date(2023, 10, 1))
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get", new_callable=AsyncMock,
                 return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.async_validate_period_open",
                 new_callable=AsyncMock)
    upload_file = UploadFile(filename="test", file=BytesIO(b""))
    with pytest.raises(InvalidAdjustmentFilenameError) as exc:
        await adjustment_service.upload_attachment(async_db_mock, 1, upload_file, 1)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_upload_attachment_invalid_ext(async_db_mock, mocker):
    request = AdjustmentRequest(id=1, user_id=1, target_date=date(2023, 10, 1))
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get", new_callable=AsyncMock,
                 return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.async_validate_period_open",
                 new_callable=AsyncMock)
    upload_file = UploadFile(filename="test.txt", file=BytesIO(b""))
    with pytest.raises(InvalidAttachmentFormatError) as exc:
        await adjustment_service.upload_attachment(async_db_mock, 1, upload_file, 1)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_upload_attachment_invalid_content(async_db_mock, mocker):
    request = AdjustmentRequest(id=1, user_id=1, target_date=date(2023, 10, 1))
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get", new_callable=AsyncMock,
                 return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.async_validate_period_open",
                 new_callable=AsyncMock)
    upload_file = UploadFile(filename="test.png", file=BytesIO(b"invalid"))
    with pytest.raises(CorruptedAttachmentError) as exc:
        await adjustment_service.upload_attachment(async_db_mock, 1, upload_file, 1)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_upload_attachment_success(async_db_mock, mocker):
    request = AdjustmentRequest(id=1, user_id=1, target_date=date(2023, 10, 1))
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get", new_callable=AsyncMock,
                 return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.async_validate_period_open",
                 new_callable=AsyncMock)

    file_content = b"%PDF-1.4..."
    file = UploadFile(filename="test.pdf", file=BytesIO(file_content))

    mocker.patch("shutil.copyfileobj")
    mocker.patch("builtins.open", mocker.mock_open())
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.create_attachment",
                 new_callable=AsyncMock,
                 return_value="Attachment")
    mocker.patch("app.features.system.audit_service.audit_service.async_log_change", new_callable=AsyncMock)

    res = await adjustment_service.upload_attachment(async_db_mock, 1, file, 1)
    assert res == "Attachment"


@pytest.mark.asyncio
async def test_approve_adjustment_not_found(async_db_mock, mocker):
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get", new_callable=AsyncMock,
                 return_value=None)
    with pytest.raises(AdjustmentNotFoundError) as exc:
        await adjustment_service.approve_adjustment(async_db_mock, 1, 99)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_reject_adjustment_not_found(async_db_mock, mocker):
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get", new_callable=AsyncMock,
                 return_value=None)
    with pytest.raises(AdjustmentNotFoundError) as exc:
        await adjustment_service.reject_adjustment(async_db_mock, 1, 99, "comentario")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_revert_adjustment_action_waiver(async_db_mock):
    request = AdjustmentRequest(id=1, adjustment_type=AdjustmentType.WAIVER)
    await adjustment_service._revert_adjustment_action(async_db_mock, request, 99)


@pytest.mark.asyncio
async def test_revert_adjustment_action_delete_punch(async_db_mock, mocker):
    request = AdjustmentRequest(user_id=1, target_date=date(2023, 10, 1), time=time(8, 0),
                                adjustment_type=AdjustmentType.DELETE_PUNCH, record_type=RecordType.ENTRY)
    record = TimeRecord(id=1)
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = record
    async_db_mock.scalars.return_value = mock_scalars

    await adjustment_service._revert_adjustment_action(async_db_mock, request, 99)
    assert record.is_ignored is False
    assert record.deleted_at is None


@pytest.mark.asyncio
async def test_revert_adjustment_status_not_found(async_db_mock, mocker):
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get", new_callable=AsyncMock,
                 return_value=None)
    with pytest.raises(AdjustmentNotFoundError) as exc:
        await adjustment_service.revert_adjustment_status(async_db_mock, 1, 99, AdjustmentStatus.PENDING, "motivo")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_revert_adjustment_status_same(async_db_mock, mocker):
    request = AdjustmentRequest(id=1, target_date=date(2023, 10, 1), status=AdjustmentStatus.PENDING)
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get", new_callable=AsyncMock,
                 return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.async_validate_period_open",
                 new_callable=AsyncMock)
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._enrich_adjustments_with_records",
                 new_callable=AsyncMock,
                 return_value=[request])

    res = await adjustment_service.revert_adjustment_status(async_db_mock, 1, 99, AdjustmentStatus.PENDING, "motivo")
    assert res.status == AdjustmentStatus.PENDING


@pytest.mark.asyncio
async def test_revert_adjustment_status_approve(async_db_mock, mocker):
    request = AdjustmentRequest(id=1, target_date=date(2023, 10, 1), status=AdjustmentStatus.PENDING,
                                adjustment_type=AdjustmentType.FORGOT_PUNCH)
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get", new_callable=AsyncMock,
                 return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.async_validate_period_open",
                 new_callable=AsyncMock)
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._execute_adjustment_action",
                 new_callable=AsyncMock)
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.update_status",
                 new_callable=AsyncMock,
                 return_value=AdjustmentRequest(id=1, status=AdjustmentStatus.APPROVED))
    mocker.patch("app.features.system.audit_service.audit_service.async_log_change", new_callable=AsyncMock)
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._enrich_adjustments_with_records",
                 new_callable=AsyncMock,
                 return_value=[AdjustmentRequest(id=1, status=AdjustmentStatus.APPROVED)])

    res = await adjustment_service.revert_adjustment_status(async_db_mock, 1, 99, AdjustmentStatus.APPROVED, "motivo")
    assert res.status == AdjustmentStatus.APPROVED


@pytest.mark.asyncio
async def test_create_adjustment_extra_time_blocked(async_db_mock, mocker):
    mocker.patch("app.features.payroll.payroll_service.payroll_service.async_validate_period_open", new_callable=AsyncMock)
    obj_in = AdjustmentRequestCreate(
        adjustment_type=AdjustmentType.EXTRA_TIME,
        record_type=RecordType.ENTRY,
        target_date=date(2026, 8, 1),
        time=time(18, 0),
        reason_text="Extra manual"
    )
    with pytest.raises(HTTPException) as exc:
        await adjustment_service.create_adjustment_request(async_db_mock, user_id=1, obj_in=obj_in)
    assert exc.value.status_code == 400
    assert "Hora extra manual foi descontinuada" in exc.value.detail


@pytest.mark.asyncio
async def test_approve_daily_excess_partial_hours(async_db_mock, mocker):
    request = AdjustmentRequest(
        id=10,
        user_id=1,
        target_date=date(2026, 8, 1),
        adjustment_type=AdjustmentType.DAILY_EXCESS,
        status=AdjustmentStatus.PENDING,
        amount_hours=2.0,
    )
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get", new_callable=AsyncMock,
                 return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.async_validate_period_open", new_callable=AsyncMock)
    mock_update = mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.update_status", new_callable=AsyncMock,
                               return_value=request)
    mocker.patch("app.features.system.audit_service.audit_service.async_log_change", new_callable=AsyncMock)
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._enrich_adjustments_with_records",
                 new_callable=AsyncMock, return_value=[request])

    await adjustment_service.approve_adjustment(
        async_db_mock,
        request_id=10,
        manager_id=99,
        comment="Aprovado 1h",
        approved_amount_hours=1.0
    )
    assert request.approved_amount_hours == 1.0
    mock_update.assert_called_once_with(async_db_mock, request, AdjustmentStatus.APPROVED, 99, "Aprovado 1h")


@pytest.mark.asyncio
async def test_revert_adjustment_status_approve_daily_excess(async_db_mock, mocker):
    request = AdjustmentRequest(
        id=24,
        user_id=4,
        target_date=date(2026, 9, 1),
        status=AdjustmentStatus.PENDING,
        adjustment_type=AdjustmentType.DAILY_EXCESS,
        amount_hours=2.0,
    )
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.get", new_callable=AsyncMock,
                 return_value=request)
    mocker.patch("app.features.payroll.payroll_service.payroll_service.async_validate_period_open",
                 new_callable=AsyncMock)
    mock_exec = mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._execute_adjustment_action",
                             new_callable=AsyncMock)
    mocker.patch("app.features.adjustments.adjustment_service.async_adjustment_repository.update_status",
                 new_callable=AsyncMock,
                 return_value=request)
    mocker.patch("app.features.system.audit_service.audit_service.async_log_change", new_callable=AsyncMock)
    mocker.patch("app.features.adjustments.adjustment_service.AdjustmentService._enrich_adjustments_with_records",
                 new_callable=AsyncMock,
                 return_value=[request])

    res = await adjustment_service.revert_adjustment_status(async_db_mock, 24, 99, AdjustmentStatus.APPROVED,
                                                            "Revertendo para aprovado")
    assert res.id == 24
    mock_exec.assert_not_called()


def test_adjustment_service_repo_property():
    custom_repo = MagicMock()
    original_repo = adjustment_service.repo
    try:
        adjustment_service.repo = custom_repo
        assert adjustment_service.repo == custom_repo
    finally:
        adjustment_service.repo = original_repo


@pytest.mark.asyncio
async def test_validate_period_open_sync_fallback(mocker, async_db_mock):
    from app.features.payroll.payroll_service import PayrollService, payroll_service
    mocker.patch.object(payroll_service, "validate_period_open")
    orig_async = getattr(PayrollService, "async_validate_period_open", None)
    try:
        delattr(PayrollService, "async_validate_period_open")
        await adjustment_service._validate_period_open(async_db_mock, date(2026, 8, 1))
        payroll_service.validate_period_open.assert_called_once()
    finally:
        if orig_async is not None:
            PayrollService.async_validate_period_open = orig_async


@pytest.mark.asyncio
async def test_reprocess_daily_excess_crossing_december(async_db_mock, mocker):
    from app.features.adjustments.adjustment_schemas import BulkReprocessDailyExcessRequest
    req = BulkReprocessDailyExcessRequest(
        user_ids=[1],
        start_date=date(2026, 12, 15),
        end_date=date(2027, 1, 10),
        overwrite_reviewed=False,
    )
    mocker.patch.object(adjustment_service, "_validate_period_open", new_callable=AsyncMock)
    bg = MagicMock()
    user = User(id=1, role=UserRole.MAINTAINER)
    res = await adjustment_service.reprocess_historical_daily_excess(async_db_mock, req, bg, current_user=user)
    assert "Reprocessamento de excedente" in res["message"]
