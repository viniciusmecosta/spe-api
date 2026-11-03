import hashlib
import json
from datetime import date, datetime, time
from enum import Enum
from typing import Any


def _canonicalize(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _canonicalize(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple, set)):
        return [_canonicalize(item) for item in value]
    if hasattr(value, "model_dump"):
        return _canonicalize(value.model_dump(mode="json"))
    return str(value)


def compute_document_hash(kind: str, payload: Any) -> str:
    canonical = {"kind": kind, "payload": _canonicalize(payload)}
    encoded = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _company_snapshot(company: Any) -> dict[str, Any]:
    if company is None:
        return {}
    return {
        "id": getattr(company, "id", None),
        "name": getattr(company, "name", None),
        "cnpj": getattr(company, "cnpj", None),
    }


def _user_snapshot(user: Any) -> dict[str, Any]:
    return {
        "id": getattr(user, "id", None),
        "name": getattr(user, "name", None),
        "cpf": getattr(user, "cpf", None),
        "pis": getattr(user, "pis", None),
        "role_title": getattr(user, "role_title", None),
    }


def compute_excel_authenticity_hash(
    month: int,
    year: int,
    start_date: date,
    end_date: date,
    company: Any,
    user_reports: Any,
) -> str:
    reports_snapshot = []
    for user, report in user_reports or []:
        raw_days = getattr(report, "daily_details", None) or getattr(report, "days", None) or []
        days_snapshot = [
            {
                "date": getattr(day, "date", None),
                "punches": list(getattr(day, "punches", []) or []),
                "worked_time": getattr(day, "worked_time", None),
                "accounted_time": getattr(day, "accounted_time", None),
                "unapproved_extra_time": getattr(day, "unapproved_extra_time", None),
                "status": getattr(day, "status", None),
            }
            for day in raw_days
        ]
        summary = getattr(report, "summary", None)
        reports_snapshot.append(
            {
                "user": _user_snapshot(user),
                "summary": {
                    "days_worked": getattr(summary, "days_worked", None),
                    "total_accounted_minutes": getattr(summary, "total_accounted_minutes", None),
                    "total_worked_time": getattr(summary, "total_worked_time", None),
                    "total_expected_time": getattr(summary, "total_expected_time", None),
                },
                "days": days_snapshot,
            }
        )
    return compute_document_hash(
        "excel_report",
        {
            "month": month,
            "year": year,
            "start_date": start_date,
            "end_date": end_date,
            "company": _company_snapshot(company),
            "reports": reports_snapshot,
        },
    )


def compute_timesheet_authenticity_hash(
    user: Any,
    company: Any,
    month: int,
    year: int,
    start_date: date,
    end_date: date,
    records: Any,
    holidays: Any,
    adjustments: Any,
    period_result: Any,
) -> str:
    records_snapshot = [
        {
            "id": getattr(record, "id", None),
            "record_datetime": getattr(record, "record_datetime", None),
            "record_type": getattr(record, "record_type", None),
            "is_ignored": getattr(record, "is_ignored", False),
        }
        for record in (records or [])
    ]
    holidays_snapshot = [
        {
            "id": getattr(holiday, "id", None),
            "date": getattr(holiday, "date", None),
            "name": getattr(holiday, "name", None),
        }
        for holiday in (holidays or [])
    ]
    adjustments_snapshot = [
        {
            "id": getattr(adj, "id", None),
            "target_date": getattr(adj, "target_date", None),
            "adjustment_type": getattr(adj, "adjustment_type", None),
            "status": getattr(adj, "status", None),
            "amount_hours": getattr(adj, "amount_hours", None),
            "approved_amount_hours": getattr(adj, "approved_amount_hours", None),
        }
        for adj in (adjustments or [])
    ]
    daily_results = getattr(period_result, "daily_results", None) or {}
    daily_snapshot = {
        str(day_key): {
            "punch_blocks": list(getattr(res, "punch_blocks", []) or []),
            "total_duration": getattr(res, "total_duration", 0),
            "accounted_duration": getattr(res, "accounted_duration", 0),
            "unapproved_extra_seconds": getattr(res, "unapproved_extra_seconds", 0),
            "waiver_seconds": getattr(res, "waiver_seconds", 0),
        }
        for day_key, res in sorted(daily_results.items(), key=lambda item: str(item[0]))
    }
    return compute_document_hash(
        "timesheet_pdf",
        {
            "user": _user_snapshot(user),
            "company": _company_snapshot(company),
            "month": month,
            "year": year,
            "start_date": start_date,
            "end_date": end_date,
            "records": records_snapshot,
            "holidays": holidays_snapshot,
            "adjustments": adjustments_snapshot,
            "daily_results": daily_snapshot,
        },
    )


def compute_receipt_authenticity_hash(data: dict[str, Any]) -> str:
    return compute_document_hash(
        "time_record_receipt",
        {
            "company_name": data.get("company_name"),
            "company_cnpj": data.get("company_cnpj"),
            "employee_name": data.get("employee_name"),
            "employee_cpf": data.get("employee_cpf"),
            "employee_pis": data.get("employee_pis"),
            "record_date": data.get("record_date"),
            "record_time": data.get("record_time"),
            "record_type_str": data.get("record_type_str"),
            "device_name": data.get("device_name"),
            "nsr": data.get("nsr"),
            "short_id": data.get("short_id"),
        },
    )


def compute_operational_export_authenticity_hash(payload: dict[str, Any]) -> str:
    filtered = {k: v for k, v in payload.items() if k not in ("gerado_em", "metadados")}
    return compute_document_hash("operational_export", filtered)
