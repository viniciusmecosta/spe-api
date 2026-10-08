import argparse
import json
from datetime import date
from pathlib import Path

from sqlalchemy import select

from app.database.session import SessionLocal
from app.features.daily_summaries.daily_summary_models import DailySummary


def _minutes(value: str) -> int:
    hours, minutes = map(int, value.split(":"))
    return hours * 60 + minutes


def verify(golden: Path) -> list[str]:
    errors = []
    with SessionLocal() as session:
        for json_path in sorted(golden.glob("????-??.json")):
            users = json.loads(json_path.read_text(encoding="utf-8"))
            for user_id_text, report in users.items():
                user_id = int(user_id_text)
                for item in report["daily_details"]:
                    day = date.fromisoformat(item["date"])
                    row = session.execute(
                        select(DailySummary.__table__).where(
                            DailySummary.__table__.c.user_id == user_id,
                            DailySummary.__table__.c.apuration_date == day,
                        )
                    ).mappings().first()
                    if row is None:
                        errors.append(f"{user_id}/{day}: missing summary")
                        continue
                    net = item["worked_minutes"]
                    waiver = sum(
                        _minutes(punch.split("Abono: ", 1)[1])
                        for punch in item["punches"]
                        if punch.startswith("Abono: ")
                    )
                    expected = {
                        "worked_minutes": net + _minutes(item["unapproved_extra_time"]),
                        "accounted_minutes": _minutes(item["accounted_time"]),
                        "expected_minutes": _minutes(item["expected_time"]),
                        "missing_minutes": max(0, _minutes(item["expected_time"]) - net),
                        "waiver_minutes": waiver,
                    }
                    for field, value in expected.items():
                        if row[field] != value:
                            errors.append(
                                f"{user_id}/{day}/{field}: {row[field]} != {value}"
                            )
    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare daily summaries with pre-migration reports")
    parser.add_argument("golden", type=Path)
    args = parser.parse_args()
    errors = verify(args.golden)
    for error in errors[:100]:
        print(error)
    print(f"Differences: {len(errors)}")
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
