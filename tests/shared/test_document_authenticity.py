from datetime import date, datetime, time
from types import SimpleNamespace

from openpyxl import load_workbook
from pydantic import BaseModel

from app.features.reports.excel_workbook_builder import ExcelWorkbookBuilder
from app.features.time_records.receipt_service import ReceiptService
from app.features.timesheets.timesheet_pdf_builder import TimesheetPdfBuilder
from app.shared.document_authenticity import (
    compute_document_hash,
    compute_excel_authenticity_hash,
    compute_operational_export_authenticity_hash,
    compute_receipt_authenticity_hash,
    compute_timesheet_authenticity_hash,
)
from app.shared.enums import AdjustmentStatus, AdjustmentType, RecordType


class _SampleModel(BaseModel):
    label: str
    when: time


def test_canonicalize_and_compute_document_hash_determinism():
    first = compute_document_hash(
        "custom",
        {
            "b": [None, 1, RecordType.ENTRY, date(2026, 8, 1), datetime(2026, 8, 1, 8, 0)],
            "a": _SampleModel(label="ok", when=time(12, 0)),
            "c": SimpleNamespace(raw="obj"),
        },
    )
    second = compute_document_hash(
        "custom",
        {
            "c": SimpleNamespace(raw="obj"),
            "a": _SampleModel(label="ok", when=time(12, 0)),
            "b": [None, 1, RecordType.ENTRY, date(2026, 8, 1), datetime(2026, 8, 1, 8, 0)],
        },
    )
    assert len(first) == 64
    assert first == second


def test_excel_workbook_embeds_deterministic_authenticity_hash():
    company = SimpleNamespace(
        id=1,
        name="Empresa Teste",
        cnpj="11222333000181",
        address="Rua A",
        phone="85999999999",
        logo_url=None,
    )
    user = SimpleNamespace(
        id=10,
        name="Colaborador",
        cpf="12345678901",
        pis="12345678901",
        role="EMPLOYEE",
        role_title="Analista",
        phone=None,
        endereco=None,
        work_schedules=[],
        current_schedules_rel=[],
        work_schedule_configs=[],
        historical_schedules=[],
    )
    day = SimpleNamespace(
        date=date(2026, 8, 1),
        day_name="Sáb",
        punches=["08:00 - 12:00"],
        worked_time="04:00",
        accounted_time="04:00",
        unapproved_extra_time="00:00",
        is_holiday=False,
        holiday_name=None,
        is_weekend=True,
        status="Normal",
    )
    summary = SimpleNamespace(
        user_name="Colaborador",
        days_worked=1,
        total_accounted_minutes=240,
        total_worked_time="04:00",
        total_expected_time="04:00",
    )
    report = SimpleNamespace(
        summary=summary,
        daily_details=[day],
    )
    expected_hash = compute_excel_authenticity_hash(
        month=8,
        year=2026,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 1),
        company=company,
        user_reports=[(user, report)],
    )
    stream = ExcelWorkbookBuilder().build(
        month=8,
        year=2026,
        user_reports=[(user, report)],
        company=company,
        logo_path=None,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 1),
    )
    wb = load_workbook(stream)
    assert wb.properties.keywords == f"sha256:{expected_hash}"
    assert wb.properties.identifier == expected_hash
    assert f"sha256:{expected_hash}" in (wb.properties.subject or "")


def test_timesheet_pdf_embeds_deterministic_authenticity_hash():
    user = SimpleNamespace(
        id=10,
        name="Colaborador",
        cpf="12345678901",
        pis="12345678901",
        role="EMPLOYEE",
        role_title="Analista",
        work_schedules=[],
        current_schedules_rel=[],
        work_schedule_configs=[],
        historical_schedules=[],
    )
    record = SimpleNamespace(
        id=5,
        record_datetime=datetime(2026, 8, 3, 8, 0),
        record_type=RecordType.ENTRY,
        is_ignored=False,
    )
    holiday = SimpleNamespace(id=2, date=date(2026, 8, 3), name="Feriado Local")
    adj = SimpleNamespace(
        id=3,
        target_date=date(2026, 8, 3),
        adjustment_type=AdjustmentType.WAIVER,
        status=AdjustmentStatus.APPROVED,
        amount_hours=4.0,
        approved_amount_hours=4.0,
        reason="Atestado",
    )
    daily_res = SimpleNamespace(
        punch_blocks=["08:00 - 12:00"],
        total_duration=14400,
        accounted_duration=14400,
        unapproved_extra_seconds=0,
        waiver_seconds=0,
        has_open_punch=False,
    )
    period_result = SimpleNamespace(
        daily_results={date(2026, 8, 3): daily_res},
        daily_is_holiday={date(2026, 8, 3): True},
        daily_expected_seconds={date(2026, 8, 3): 14400},
        daily_accounted_results={date(2026, 8, 3): SimpleNamespace(accounted_seconds=14400)},
    )
    expected_hash = compute_timesheet_authenticity_hash(
        user=user,
        company=None,
        month=8,
        year=2026,
        start_date=date(2026, 8, 3),
        end_date=date(2026, 8, 3),
        records=[record],
        holidays=[holiday],
        adjustments=[adj],
        period_result=period_result,
    )
    pdf_stream = TimesheetPdfBuilder().build(
        user=user,
        company=None,
        month=8,
        year=2026,
        start_date=date(2026, 8, 3),
        end_date=date(2026, 8, 3),
        today=date(2026, 8, 3),
        records=[record],
        holidays=[holiday],
        all_adjustments=[adj],
        period_result=period_result,
    )
    pdf_bytes = pdf_stream.getvalue()
    assert f"sha256:{expected_hash}".encode("ascii") in pdf_bytes


def test_receipt_pdf_and_operational_export_authenticity_hashes():
    receipt_data = {
        "company_name": "Empresa Teste",
        "company_address": "Rua A",
        "company_cnpj": "11.222.333/0001-81",
        "employee_name": "Colaborador",
        "employee_cpf": "***.456.789-**",
        "employee_pis": "12345678901",
        "record_date": "03/08/2026",
        "record_time": "08:00",
        "record_type_str": "Entrada",
        "device_name": "Quiosque",
        "nsr": 42,
        "short_id": "ABC123",
    }
    expected_receipt_hash = compute_receipt_authenticity_hash(receipt_data)
    pdf_bytes = ReceiptService.generate_pdf_receipt(receipt_data)
    assert f"sha256:{expected_receipt_hash}".encode("ascii") in pdf_bytes

    export_payload_a = {
        "tipo": "marcacoes",
        "gerado_em": "2026-08-03T10:00:00+00:00",
        "marcacoes": [{"id": 1, "tipo": "ENTRY"}],
    }
    export_payload_b = {
        "tipo": "marcacoes",
        "gerado_em": "2026-08-04T15:30:00+00:00",
        "marcacoes": [{"id": 1, "tipo": "ENTRY"}],
    }
    assert compute_operational_export_authenticity_hash(
        export_payload_a
    ) == compute_operational_export_authenticity_hash(export_payload_b)
