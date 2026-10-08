from datetime import datetime

from app.features.time_records.time_record_formatters import format_daily_records
from app.features.time_records.time_record_models import TimeRecord
from app.shared.enums import RecordType


def test_format_daily_records_closes_previous_open_entry_and_keeps_trailing_entry():
    records = [
        TimeRecord(record_type=RecordType.ENTRY, record_datetime=datetime(2026, 10, 5, 8, 0)),
        TimeRecord(record_type=RecordType.ENTRY, record_datetime=datetime(2026, 10, 5, 9, 0)),
    ]

    entries, exits, punches, blocks = format_daily_records(records)

    assert entries == ["08:00", "09:00"]
    assert exits == []
    assert punches == ["08:00 (E)", "09:00 (E)"]
    assert blocks == ["08:00 - --:--", "09:00 - --:--"]
