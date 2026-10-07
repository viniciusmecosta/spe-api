import argparse
import asyncio
import hashlib
import importlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import extract, select

from app.core.config import settings
from app.database.session import SessionLocal
from app.features.payroll.payroll_models import PayrollClosure
from app.features.reports.excel_service import excel_service
from app.features.reports.report_service import report_service
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import User


OUTPUT_ROOT = Path("backups/golden")
MODEL_MODULES = (
    "app.features.printers.printer_models",
    "app.features.devices.device_models",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


async def capture(output: Path) -> dict:
    for module in MODEL_MODULES:
        importlib.import_module(module)
    if output.exists():
        raise FileExistsError(f"Snapshot already exists: {output}")
    output.mkdir(parents=True)
    manifest: dict = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), "periods": {}}

    with SessionLocal() as session:
        record_year = extract("year", TimeRecord.record_datetime)
        record_month = extract("month", TimeRecord.record_datetime)
        periods = session.execute(
            select(record_year, record_month).distinct().order_by(record_year, record_month)
        ).all()
        user_ids = session.scalars(select(User.id).order_by(User.id)).all()

        for year_value, month_value in periods:
            year, month = int(year_value), int(month_value)
            key = f"{year:04d}-{month:02d}"
            print(f"Capturing {key}", flush=True)
            reports = {}
            for user_id in user_ids:
                report = await report_service.get_advanced_user_report(
                    session, user_id, month, year
                )
                if report is not None:
                    reports[str(user_id)] = report.model_dump(mode="json")

            json_path = output / f"{key}.json"
            json_path.write_text(
                json.dumps(reports, ensure_ascii=False, sort_keys=True, indent=2),
                encoding="utf-8",
            )
            excel_path = output / f"{key}.xlsx"
            workbook = await excel_service.generate_excel_report(session, month, year)
            excel_path.write_bytes(workbook.getvalue())
            period_files = {
                json_path.name: _sha256(json_path),
                excel_path.name: _sha256(excel_path),
            }

            closure = session.scalar(
                select(PayrollClosure).where(
                    PayrollClosure.year == year,
                    PayrollClosure.month == month,
                    PayrollClosure.is_closed.is_(True),
                    PayrollClosure.deleted_at.is_(None),
                )
            )
            if closure and closure.report_path:
                official = Path(closure.report_path)
                if not official.is_absolute():
                    official = Path(settings.UPLOAD_DIR) / official
                if official.is_file():
                    copy_path = output / f"{key}-official.xlsx"
                    shutil.copy2(official, copy_path)
                    period_files[copy_path.name] = _sha256(copy_path)
                else:
                    period_files["official_report_missing"] = str(official)

            manifest["periods"][key] = {"users": len(reports), "files": period_files}

    manifest_path = output / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture current apuration reports")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--use-summaries", action="store_true")
    args = parser.parse_args()
    if args.use_summaries:
        settings.DAILY_SUMMARY_READ_ENABLED = True
    output = args.output.resolve()
    if OUTPUT_ROOT.resolve() not in output.parents:
        parser.error("--output must be a new directory inside backups/golden/")
    manifest = asyncio.run(capture(output))
    print(f"Captured {len(manifest['periods'])} periods at {output}")


if __name__ == "__main__":
    main()
