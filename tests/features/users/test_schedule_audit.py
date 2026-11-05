import base64
import json
import zlib
from datetime import date, time
from types import SimpleNamespace

from sqlalchemy import create_engine

from app.features.users.schedule_audit import (
    _format_clock,
    schedule_audit_data,
)


def test_schedule_audit_groups_matching_days_like_excel_without_zlib_bloat():
    mon = SimpleNamespace(
        id=1, user_id=7, day_of_week=0, daily_minutes=480,
        entry_1=time(8), exit_1=time(12), entry_2=time(14), exit_2=time(18),
        is_daily_excess_enabled=True,
    )
    tue = SimpleNamespace(
        id=2, user_id=7, day_of_week=1, daily_minutes=480,
        entry_1=time(8), exit_1=time(12), entry_2=time(14), exit_2=time(18),
        is_daily_excess_enabled=True,
    )
    wed = SimpleNamespace(
        id=3, user_id=7, day_of_week=2, daily_minutes=480,
        entry_1=time(8), exit_1=time(12), entry_2=time(14), exit_2=time(18),
        is_daily_excess_enabled=True,
    )
    sat = SimpleNamespace(
        id=4, user_id=7, day_of_week=5, daily_minutes=240,
        entry_1=time(8), exit_1=time(12, 0, 15), entry_2=None, exit_2=None,
        is_daily_excess_enabled=False,
    )
    result = schedule_audit_data([mon, tue, wed, sat], date(2026, 9, 1), date(2026, 9, 30))
    snapshot = json.loads(zlib.decompress(base64.b64decode(result.pop("schedule_snapshot_zlib")[3:])))
    assert len(snapshot["schedules"]) == 4
    assert result == {
        "valid_from": "2026-09-01",
        "valid_until": "2026-09-30",
        "schedule_summary": (
            "Funcionário #7: Segunda a Quarta: 08:00 às 12:00 e 14:00 às 18:00 "
            "(480 min; excedente: sim); Sábado: 08:00 às 12:00:15 (240 min; excedente: não)"
        ),
    }


def test_schedule_audit_does_not_invent_absent_hours_or_dates():
    config = SimpleNamespace(
        id=None, user_id=1, day_of_week=6, daily_minutes=0,
        entry_1=None, exit_1=None, entry_2=None, exit_2=None,
        is_daily_excess_enabled=None,
    )
    result = schedule_audit_data([config], None, None)
    assert result["valid_from"] is None
    assert result["valid_until"] is None
    assert "Domingo: sem horários informados (0 min; excedente: não informado)" in result["schedule_summary"]
    named = schedule_audit_data([config], None, None, {1: "Maria"})
    assert "Funcionário Maria (#1)" in named["schedule_summary"]


def test_schedule_audit_handles_dict_inputs_and_edge_cases():
    assert _format_clock("   ") is None
    assert _format_clock("08:30:00") == "08:30"
    assert _format_clock("08:30:45") == "08:30:45"
    dict_items = [
        {"user_id": None, "day_of_week": None, "daily_hours": 8.0, "entry_1": "08:00:00"},
        {"user_id": 2, "day_of_week": 0, "entry_1": "09:00"},
    ]
    res = schedule_audit_data(dict_items, "2026-09-01", "2026-09-30")
    assert "Funcionário não informado: Dia não informado: 08:00 às não informado (480 min)" in res["schedule_summary"]
    assert "Funcionário #2: Segunda: 09:00 às não informado" in res["schedule_summary"]


async def test_schedule_lock_and_service_edge_branches(async_db_mock, db_session_mock, mocker):
    from datetime import datetime
    from unittest.mock import AsyncMock, MagicMock

    import pytest
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.database.schedule_lock import lock_schedule_mutations
    from app.features.adjustments.adjustment_exceptions import ExcessApprovalLimitError
    from app.features.adjustments.adjustment_schemas import AdjustmentWaiverCreate
    from app.features.adjustments.adjustment_service import AdjustmentService
    from app.features.payroll.payroll_repository import (
        async_payroll_repository,
        payroll_repository,
    )
    from app.features.system.audit_service import audit_service
    from app.features.system.routine_orchestrator import RoutineOrchestrator
    from app.features.time_records.time_record_schemas import normalize_input_datetime
    from app.features.time_records.time_record_service import TimeRecordService
    from app.features.users.user_exceptions import (
        BulkScheduleValidationError,
        UserNotFoundError,
    )
    from app.features.users.user_work_schedule_service import UserWorkScheduleService
    from app.shared.enums import AdjustmentStatus, AdjustmentType, RecordType

    pg_engine = create_engine("sqlite://")
    pg_engine.dialect.name = "postgresql"
    pg_session = MagicMock()
    pg_session.get_bind.return_value = pg_engine
    lock_schedule_mutations(pg_session)
    pg_session.execute.assert_called_once()
    pg_engine.dispose()

    sched_service = UserWorkScheduleService(async_db_mock)
    assert await sched_service._schedule_user_names(async_db_mock, set()) == {}
    async_spec_session = MagicMock(spec=AsyncSession)
    async_spec_session.run_sync = AsyncMock()
    await sched_service._lock_mutations(async_spec_session)
    async_spec_session.run_sync.assert_awaited_once_with(lock_schedule_mutations)

    dup_users = [{"user_id": 1, "schedules": [{"day_of_week": 0}, {"day_of_week": 0}]}]
    with pytest.raises(BulkScheduleValidationError):
        sched_service._validate_schedule_days(dup_users)

    old_diff, new_diff = audit_service.compute_diffs(
        {"valid_from": "2026-09-01", "valid_until": "2026-09-30", "schedule_summary": "A"},
        {"valid_from": "2026-09-01", "valid_until": "2026-09-30", "schedule_summary": "B"},
    )
    assert old_diff["valid_from"] == "2026-09-01"
    assert new_diff["valid_until"] == "2026-09-30"

    orchestrator = RoutineOrchestrator(async_db_mock)
    mocker.patch.object(orchestrator, "_schedule_allows_run", return_value=True)
    mocker.patch.object(orchestrator, "_already_delivered", new_callable=AsyncMock, return_value=True)
    assert await orchestrator._enqueue_routine("DAILY_REPORT", scheduled=True) is None

    db_session_mock.scalars.return_value.first.return_value = None
    assert payroll_repository.get_first_closed_in_range(
        db_session_mock, date(2026, 1, 1), date(2026, 1, 31)
    ) is None
    async_db_mock.scalars.return_value = SimpleNamespace(first=lambda: None)
    assert await async_payroll_repository.get_first_closed_in_range(
        async_db_mock, date(2026, 1, 1), date(2026, 1, 31)
    ) is None

    adj_service = AdjustmentService(async_db_mock)
    mocker.patch("app.features.adjustments.adjustment_service.async_user_repository.get", new_callable=AsyncMock, return_value=None)
    waiver_in = AdjustmentWaiverCreate(user_id=99, target_date=date(2026, 8, 1), amount_hours=2.0, reason_text="Motivo")
    with pytest.raises(UserNotFoundError):
        await adj_service.create_manager_waiver(async_db_mock, waiver_in, 1)

    excess_req = SimpleNamespace(
        id=1,
        target_date=date(2026, 8, 1),
        status=AdjustmentStatus.PENDING,
        adjustment_type=AdjustmentType.DAILY_EXCESS,
        amount_hours=1.0,
        amount_minutes=60,
    )
    mocker.patch.object(adj_service.repo, "lock", new_callable=AsyncMock)
    mocker.patch.object(adj_service.repo, "get", new_callable=AsyncMock, return_value=excess_req)
    mocker.patch.object(adj_service, "_validate_period_open", new_callable=AsyncMock)
    with pytest.raises(ExcessApprovalLimitError):
        await adj_service.approve_adjustment(async_db_mock, 1, 2, "ok", 2.0)

    mocker.patch("app.features.time_records.time_record_schemas.to_app_timezone", side_effect=OverflowError)
    bad_dt = datetime(2026, 1, 1, 12, 0)
    with pytest.raises(ValueError):
        normalize_input_datetime(bad_dt)

    tr_service = TimeRecordService(async_spec_session)
    existing_rec = SimpleNamespace(
        id=10,
        user_id=1,
        record_type=RecordType.ENTRY,
        record_datetime=datetime(2026, 8, 1, 8, 0),
        is_ignored=False,
        nsr=1,
        device_id=None,
    )
    async_spec_session.sync_session = MagicMock()
    async_spec_session.flush = AsyncMock()
    async_spec_session.refresh = AsyncMock()
    mocker.patch.object(tr_service.repo, "get", new_callable=AsyncMock, return_value=existing_rec)
    mocker.patch("app.features.time_records.time_record_service.time_record_change_service.validate_period_open", new_callable=AsyncMock)
    mocker.patch.object(tr_service, "_process_toggle_invalidations", new_callable=AsyncMock)
    mocker.patch.object(tr_service, "_create_toggled_record", return_value=existing_rec)
    mocker.patch.object(tr_service, "_commit_and_audit_toggle_record", new_callable=AsyncMock)
    manager = SimpleNamespace(id=1, role="MANAGER")
    await tr_service.toggle_record_type.__wrapped__(tr_service, async_spec_session, 10, manager)
    async_spec_session.refresh.assert_any_await(existing_rec, ["editor"])


async def test_remaining_service_and_helper_branches(async_db_mock, tmp_path, mocker):
    from datetime import datetime
    from unittest.mock import AsyncMock, MagicMock

    import pytest
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.core.exceptions import DomainException
    from app.features.companies.company_schemas import _validate_cnpj_optional
    from app.features.companies.company_service import company_service
    from app.features.printers.printer_service import printer_service
    from app.features.reports.report_response_builder import ReportResponseBuilder
    from app.features.system.backup_manifest import validate_manifest_file
    from app.features.time_records.time_record_admin_service import (
        TimeRecordAdminService,
    )
    from app.features.time_records.time_record_schemas import (
        TimeRecordCreateAdmin,
        TimeRecordUpdate,
    )
    from app.shared.enums import AdjustmentStatus, AdjustmentType, RecordType
    from app.shared.sql_text import sql_lines
    from app.shared.time_calculation_service import waiver_for_calculation

    assert _validate_cnpj_optional(None) is None

    async_db_mock.get.return_value = None
    with pytest.raises(DomainException):
        await company_service._validate_default_printer(async_db_mock, 99)
    with pytest.raises(DomainException):
        await printer_service._validate_company(async_db_mock, 99)

    existing_comp = SimpleNamespace(
        id=1, name="Empresa", cnpj="11222333000181", address="Rua A",
        phone="85999999999", logo_path="old.png", default_printer_id=None,
    )
    mocker.patch.object(company_service.repo, "get_current", new_callable=AsyncMock, return_value=existing_comp)
    mocker.patch("app.features.companies.company_service.upload_storage.save", new_callable=AsyncMock, return_value=SimpleNamespace(relative_path="logo.png"))
    mocker.patch("app.features.companies.company_service.persist_changes", new_callable=AsyncMock)
    mocker.patch("app.features.companies.company_service.audit_service.async_log_change", new_callable=AsyncMock)
    mocker.patch.object(company_service, "_cleanup_old_logo", new_callable=AsyncMock, side_effect=OSError("disk"))
    await company_service.upload_logo(async_db_mock, SimpleNamespace(filename="a.png"), 1)

    d = date(2026, 8, 3)
    waiver1 = SimpleNamespace(
        id=1, user_id=1, target_date=d, adjustment_type=AdjustmentType.WAIVER,
        status=AdjustmentStatus.APPROVED, amount_hours=2.0, approved_amount_hours=None,
        reason_text="A", manager_id=None, manager_comment=None, created_at=None,
        reviewed_at=None, deleted_at=None, attachments=[],
    )
    waiver2 = SimpleNamespace(
        id=2, user_id=1, target_date=d, adjustment_type=AdjustmentType.WAIVER,
        status=AdjustmentStatus.APPROVED, amount_hours=3.0, approved_amount_hours=None,
        reason_text="B", manager_id=None, manager_comment=None, created_at=None,
        reviewed_at=None, deleted_at=None, attachments=[],
    )
    assert waiver_for_calculation([waiver1]) is waiver1
    assert waiver_for_calculation([waiver1, waiver2]).amount_hours == 5.0

    builder = ReportResponseBuilder()
    period_res = SimpleNamespace(
        daily_results={d: SimpleNamespace(gross_worked_seconds=0)},
        daily_waivers={d: waiver1},
        daily_accounted_results={
            d: SimpleNamespace(
                accounted_seconds=0, excess_seconds=0, is_daily_excess_enabled=False,
                expected_seconds=28800, unapproved_extra_seconds=0,
            )
        },
    )
    hist_day = builder._build_history_day(
        current=d, today_date=d, records=[], holidays=[], anomalies=[],
        period_result=period_res, is_manager=True, day_adjustments=[waiver1, waiver2],
    )
    assert hist_day.abono_hours == 5.0

    unverified = tmp_path / "dump.sql"
    unverified.write_text("SELECT 1;\n", encoding="utf-8")
    with pytest.raises(ValueError):
        validate_manifest_file(unverified, {"users"}, allow_unverified=False)

    assert list(sql_lines(["SELECT 1 -- comentario\n"])) == ["SELECT 1 -- comentario\n"]
    scanner_gen = sql_lines(["\\copy users FROM stdin\n"], reject_psql_commands=True)
    with pytest.raises(ValueError):
        list(scanner_gen)

    async_spec = MagicMock(spec=AsyncSession)
    async_spec.sync_session = MagicMock()
    async_spec.refresh = AsyncMock()
    admin_svc = TimeRecordAdminService(async_spec)
    rec = SimpleNamespace(
        id=5, user_id=1, record_type=RecordType.ENTRY,
        record_datetime=datetime(2026, 8, 3, 8, 0), is_ignored=False,
        edited_by=None, edit_justification=None,
    )
    mocker.patch("app.features.time_records.time_record_admin_service.time_record_change_service.validate_period_open", new_callable=AsyncMock)
    mocker.patch("app.features.time_records.time_record_admin_service.time_record_change_service.is_first_entry_affected", new_callable=AsyncMock, return_value=False)
    mocker.patch.object(admin_svc.repo, "create", new_callable=AsyncMock, return_value=rec)
    mocker.patch.object(admin_svc, "_commit_and_audit_admin_create", new_callable=AsyncMock)
    create_in = TimeRecordCreateAdmin(
        user_id=1, record_type=RecordType.ENTRY,
        record_datetime=datetime(2026, 8, 3, 8, 0), edit_justification="Ajuste manual válido",
    )
    await admin_svc.create_admin_record.__wrapped__(admin_svc, async_spec, create_in, 1)

    mocker.patch.object(admin_svc, "_get_record_by_id", new_callable=AsyncMock, return_value=rec)
    mocker.patch.object(admin_svc, "_handle_admin_update_invalidations", new_callable=AsyncMock)
    mocker.patch.object(admin_svc, "_build_updated_admin_record", return_value=rec)
    mocker.patch.object(admin_svc, "_commit_and_audit_admin_update", new_callable=AsyncMock)
    update_in = TimeRecordUpdate(
        record_type=RecordType.EXIT,
        record_datetime=datetime(2026, 8, 3, 12, 0), edit_justification="Ajuste manual válido",
    )
    await admin_svc.update_admin_record.__wrapped__(admin_svc, async_spec, 5, update_in, 1)
    assert async_spec.refresh.await_count == 2
