from app.features.time_records.time_record_models import TimeRecord
from app.shared.enums import RecordType


def format_daily_records(
    records: list[TimeRecord],
) -> tuple[list[str], list[str], list[str], list[str]]:
    entries: list[str] = []
    exits: list[str] = []
    punches: list[str] = []
    blocks: list[str] = []
    entry: str | None = None
    for record in records:
        clock = record.record_datetime.strftime("%H:%M")
        if record.record_type == RecordType.ENTRY:
            punches.append(f"{clock} (E)")
            entries.append(clock)
            if entry is not None:
                blocks.append(f"{entry} - --:--")
            entry = clock
        else:
            punches.append(f"{clock} (S)")
            exits.append(clock)
            blocks.append(f"{entry or '--:--'} - {clock}")
            entry = None
    if entry is not None:
        blocks.append(f"{entry} - --:--")
    return entries, exits, punches, blocks
