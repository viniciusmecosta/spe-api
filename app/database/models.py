from importlib import import_module

from sqlalchemy import Index, text

from app.database.base import Base

MODEL_MODULES = (
    "app.features.adjustments.adjustment_models",
    "app.features.companies.company_models",
    "app.features.daily_summaries.daily_summary_models",
    "app.features.devices.device_models",
    "app.features.holidays.holiday_models",
    "app.features.payroll.payroll_models",
    "app.features.printers.printer_models",
    "app.features.system.system_models",
    "app.features.time_records.time_record_models",
    "app.features.users.user_models",
)
for module in MODEL_MODULES:
    import_module(module)

INDEXES = {
    "companies": [("ix_companies_default_printer_id", ["default_printer_id"], {})],
    "printers": [("ix_printers_company_id", ["company_id"], {})],
    "users": [
        ("idx_users_active_role", ["is_active", "role"], {}),
        (
            "idx_users_name_trgm",
            ["name"],
            {"postgresql_using": "gin", "postgresql_ops": {"name": "gin_trgm_ops"}},
        ),
    ],
    "device_credentials": [
        ("idx_device_credentials_lookup", ["api_key_hash", "key_type", "is_active"], {})
    ],
    "firmwares": [
        ("idx_firmwares_version_created", ["version", text("created_at DESC")], {})
    ],
    "user_biometrics": [
        ("ix_user_biometrics_user_id", ["user_id"], {}),
        ("idx_user_biometrics_sensor_lookup", ["sensor_index"], {}),
    ],
    "user_work_schedule_configs": [
        ("ix_user_work_schedule_configs_user_id", ["user_id"], {}),
        (
            "idx_user_work_schedules_active",
            ["user_id", "valid_from", "valid_until"],
            {},
        ),
    ],
    "time_records": [
        (
            "idx_tr_active_period",
            ["user_id", "record_datetime"],
            {"postgresql_where": text("is_ignored = FALSE")},
        ),
        *[
            (f"ix_time_records_{column}", [column], {})
            for column in (
                "biometric_id",
                "edited_by",
                "deleted_by",
                "original_record_id",
            )
        ],
    ],
    "adjustment_requests": [
        ("ix_adjustment_requests_manager_id", ["manager_id"], {}),
        ("ix_adjustment_requests_deleted_by", ["deleted_by"], {}),
    ],
    "adjustment_attachments": [
        ("ix_adjustment_attachments_request_id", ["adjustment_request_id"], {})
    ],
    "payroll_closures": [
        ("idx_payroll_closures_period", ["year", "month"], {}),
        ("ix_payroll_closures_closed_by", ["closed_by_user_id"], {}),
        ("ix_payroll_closures_deleted_by", ["deleted_by"], {}),
    ],
    "audit_logs": [
        ("idx_audit_logs_new_data_gin", ["new_data"], {"postgresql_using": "gin"}),
        ("idx_audit_logs_old_data_gin", ["old_data"], {"postgresql_using": "gin"}),
    ],
    "routine_logs": [
        ("idx_routine_logs_execution_time", [text("execution_time DESC")], {})
    ],
}

for table_name, indexes in INDEXES.items():
    table = Base.metadata.tables[table_name]
    for name, columns, options in indexes:
        if not any(index.name == name for index in table.indexes):
            Index(
                name,
                *(
                    table.c[column] if isinstance(column, str) else column
                    for column in columns
                ),
                _table=table,
                **options,
            )
