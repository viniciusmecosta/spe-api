from __future__ import annotations

TABLE_ORDER = [
    "companies",
    "printers",
    "users",
    "device_credentials",
    "firmwares",
    "holidays",
    "user_biometrics",
    "user_work_schedule_configs",
    "time_records",
    "adjustment_requests",
    "adjustment_attachments",
    "payroll_closures",
    "audit_logs",
    "routine_logs",
]

MIGRATION_TABLES = ["alembic_version", *TABLE_ORDER]

EXPECTED_COLUMNS: dict[str, set[str]] = {
    "alembic_version": {"version_num"},
    "companies": {
        "id", "name", "cnpj", "address", "phone", "logo_path",
        "auto_print_receipt", "default_printer_id",
    },
    "printers": {"id", "name", "address", "status", "paper_width", "company_id"},
    "users": {
        "id", "username", "name", "email", "cpf", "pis", "endereco",
        "data_nascimento", "password_hash", "is_active", "role",
        "can_manual_punch_desktop", "can_manual_punch_mobile",
        "can_export_report", "is_exempt_from_rules", "is_tolerance_exempt",
        "auto_print_receipt", "created_at", "updated_at",
    },
    "device_credentials": {
        "id", "name", "key_type", "api_key_hash", "is_active", "created_at", "updated_at",
    },
    "firmwares": {"id", "version", "file_path", "created_at"},
    "holidays": {"id", "date", "name"},
    "user_biometrics": {
        "id", "user_id", "sensor_index", "template_data", "finger_id", "created_at",
    },
    "user_work_schedule_configs": {
        "id", "user_id", "day_of_week", "daily_hours", "entry_1", "exit_1",
        "entry_2", "exit_2", "valid_from", "valid_until", "is_daily_excess_enabled",
    },
    "time_records": {
        "id", "user_id", "record_type", "record_datetime", "ip_address",
        "device_name", "platform", "biometric_id", "edited_by", "edit_justification",
        "deleted_at", "deleted_by", "is_ignored", "is_verified", "original_record_id",
        "created_at", "updated_at",
    },
    "adjustment_requests": {
        "id", "user_id", "adjustment_type", "record_type", "target_date", "time",
        "amount_hours", "reason_text", "status", "manager_id", "manager_comment",
        "created_at", "reviewed_at", "deleted_at", "deleted_by", "approved_amount_hours",
    },
    "adjustment_attachments": {
        "id", "adjustment_request_id", "file_path", "file_type", "uploaded_at",
    },
    "payroll_closures": {
        "id", "month", "year", "is_closed", "closed_by_user_id", "closed_at",
        "report_path", "deleted_at", "deleted_by", "reopen_observation",
    },
    "audit_logs": {
        "id", "user_id", "action", "entity", "entity_id", "old_data", "new_data", "timestamp",
    },
    "routine_logs": {
        "id", "routine_type", "execution_time", "target_date", "status", "details",
    },
}

BOOLEAN_COLUMNS = {
    "companies": {"auto_print_receipt"},
    "printers": {"status"},
    "users": {
        "is_active", "can_manual_punch_desktop", "can_manual_punch_mobile",
        "can_export_report", "is_exempt_from_rules", "is_tolerance_exempt",
        "auto_print_receipt",
    },
    "device_credentials": {"is_active"},
    "user_work_schedule_configs": {"is_daily_excess_enabled"},
    "time_records": {"is_ignored", "is_verified"},
    "payroll_closures": {"is_closed"},
}

JSONB_COLUMNS = {"audit_logs": {"old_data", "new_data"}}

TIMESTAMPTZ_COLUMNS = {
    "users": {"created_at", "updated_at"},
    "device_credentials": {"created_at", "updated_at"},
    "firmwares": {"created_at"},
    "user_biometrics": {"created_at"},
    "time_records": {"record_datetime", "deleted_at", "created_at", "updated_at"},
    "adjustment_requests": {"created_at", "reviewed_at", "deleted_at"},
    "adjustment_attachments": {"uploaded_at"},
    "payroll_closures": {"closed_at", "deleted_at"},
    "audit_logs": {"timestamp"},
    "routine_logs": {"execution_time"},
}

DATE_COLUMNS = {
    "users": {"data_nascimento"},
    "holidays": {"date"},
    "user_work_schedule_configs": {"valid_from", "valid_until"},
    "adjustment_requests": {"target_date"},
    "routine_logs": {"target_date"},
}

TIME_COLUMNS = {
    "user_work_schedule_configs": {"entry_1", "exit_1", "entry_2", "exit_2"},
    "adjustment_requests": {"time"},
}


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def normalize_boolean(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "t", "yes", "y"}:
            return True
        if normalized in {"0", "false", "f", "no", "n"}:
            return False
    raise ValueError(f"valor booleano inválido: {value!r}")


def sqlite_type_family(declared_type: str) -> str:
    declared = (declared_type or "").strip().upper()
    if declared == "BOOLEAN" or declared.startswith("BOOL"):
        return "boolean"
    if declared == "JSON" or declared.startswith("JSON"):
        return "json"
    if declared.startswith("DATETIME") or declared.startswith("TIMESTAMP"):
        return "datetime"
    if declared == "DATE" or declared.startswith("DATE("):
        return "date"
    if declared == "TIME" or declared.startswith("TIME("):
        return "time"
    if "INT" in declared:
        return "integer"
    if any(token in declared for token in ("CHAR", "CLOB", "TEXT")) or declared == "":
        return "text"
    if any(token in declared for token in ("REAL", "FLOA", "DOUB")):
        return "real"
    if "BLOB" in declared:
        return "binary"
    return "numeric"


def postgres_type_family(data_type: str, udt_name: str) -> str:
    data_type = data_type.lower()
    udt_name = udt_name.lower()
    if data_type == "boolean":
        return "boolean"
    if data_type in {"smallint", "integer", "bigint"}:
        return "integer"
    if data_type in {"real", "double precision", "numeric", "decimal"}:
        return "real"
    if data_type == "date":
        return "date"
    if data_type.startswith("time "):
        return "time"
    if data_type.startswith("timestamp "):
        return "datetime"
    if data_type in {"json", "jsonb"} or udt_name in {"json", "jsonb"}:
        return "json"
    if data_type == "bytea":
        return "binary"
    if data_type == "user-defined":
        return "enum"
    return "text"


def are_type_families_compatible(sqlite_family: str, postgres_family: str) -> bool:
    if sqlite_family == postgres_family:
        return True
    if sqlite_family == "text" and postgres_family == "enum":
        return True
    if sqlite_family == "integer" and postgres_family == "real":
        return True
    return False
