import asyncio
import json
import subprocess
import sys
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import httpx
import psycopg2
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from psycopg2 import sql
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.exceptions import DailySummaryRecalculationError
from app.database.errors import constraint_name
from app.features.companies.company_models import Company
from app.features.daily_summaries.daily_summary_models import DailySummary
from app.features.daily_summaries.daily_summary_service import daily_summary_service
from app.features.payroll.payroll_exceptions import PayrollPeriodClosedError
from app.features.payroll.payroll_models import PayrollClosure
from app.features.payroll.payroll_repository import async_payroll_repository
from app.features.payroll.payroll_service import PayrollService, payroll_service
from app.features.system.backup_manifest import add_manifest
from app.features.system.backup_service import BackupService
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import User, UserWorkScheduleConfig
from app.shared import deps
from app.shared.enums import RecordType, UserRole
from app.shared.time_calculation_service import time_calculation_service
from scripts.apply_sql_to_postgresql import apply_sql_file, restore_backup


async def seed(factory):
    async with factory() as session:
        user = User(username="audit", name="Synthetic User", role=UserRole.MAINTAINER)
        session.add(user)
        await session.commit()
        return user


def punches(user_id, day="2026-02-02"):
    return [
        TimeRecord(
            user_id=user_id,
            record_type=kind,
            record_datetime=datetime.fromisoformat(f"{day}T{clock}:00-03:00"),
        )
        for kind, clock in [(RecordType.ENTRY, "08:00"), (RecordType.EXIT, "16:00")]
    ]


@pytest.mark.asyncio
async def test_summary_failure_rolls_back_source_and_keeps_previous_summary(
    pg_session_factory,
):
    factory = pg_session_factory
    user = await seed(factory)
    day = date(2026, 2, 2)
    await daily_summary_service.calculate_day(user.id, day, False, True)
    async with factory() as session:
        session.add_all(punches(user.id))
        with patch.object(
            daily_summary_service,
            "_calculate_user_day",
            side_effect=RuntimeError("outage"),
        ):
            with pytest.raises(DailySummaryRecalculationError):
                await session.commit()
        await session.rollback()
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(TimeRecord)) == 0
        row = await session.scalar(select(DailySummary))
        assert row.worked_minutes == 0
    async with factory() as session:
        session.add_all(punches(user.id))
        await session.commit()
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(TimeRecord)) == 2
        assert (await session.scalar(select(DailySummary))).worked_minutes == 480


@pytest.mark.asyncio
async def test_retrying_commit_after_calculation_failure_refreshes_summary(
    pg_session_factory,
):
    factory = pg_session_factory
    user = await seed(factory)
    await daily_summary_service.calculate_day(user.id, date(2026, 2, 2), False, True)
    async with factory() as session:
        session.add_all(punches(user.id))
        with patch.object(
            daily_summary_service,
            "_calculate_user_day",
            side_effect=RuntimeError("outage"),
        ):
            with pytest.raises(DailySummaryRecalculationError):
                await session.commit()
        await session.commit()
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(TimeRecord)) == 2
        assert (await session.scalar(select(DailySummary))).worked_minutes == 480


@pytest.mark.asyncio
async def test_utc_admin_request_cannot_write_closed_local_month(pg_session_factory):
    from app.main import app

    user = await seed(pg_session_factory)
    async with pg_session_factory() as session:
        session.add(PayrollClosure(month=1, year=2026, closed_by_user_id=user.id))
        await session.commit()
    app.dependency_overrides[deps.get_current_manager] = lambda: user
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/time-records/admin",
                json={
                    "user_id": user.id,
                    "record_type": "EXIT",
                    "record_datetime": "2026-02-01T00:30:00Z",
                    "edit_justification": "timezone regression",
                },
            )
        assert response.status_code == 400
    finally:
        app.dependency_overrides.pop(deps.get_current_manager, None)
    async with pg_session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(TimeRecord)) == 0


@pytest.mark.asyncio
async def test_closing_first_rejects_a_writer_that_validated_an_open_month(
    pg_session_factory,
):
    factory = pg_session_factory
    user = await seed(factory)
    async with factory() as writer:
        await payroll_service.async_validate_period_open(writer, date(2026, 3, 2))
        async with factory() as closer:
            await async_payroll_repository.create(
                closer, month=3, year=2026, user_id=user.id
            )
        writer.add_all(punches(user.id, "2026-03-02"))
        with pytest.raises(PayrollPeriodClosedError):
            await writer.commit()
        await writer.rollback()
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(TimeRecord)) == 0


@pytest.mark.asyncio
async def test_closing_waits_for_the_writer_and_exports_its_summary(pg_session_factory):
    from fastapi import BackgroundTasks
    from app.features.reports.excel_service import excel_service

    factory = pg_session_factory
    user = await seed(factory)
    ready = asyncio.Event()
    observed = []

    async def generate(session, *args):
        observed.append(
            await session.scalar(select(func.sum(DailySummary.worked_minutes)))
        )
        return BytesIO(b"synthetic workbook")

    async def close():
        async with factory() as session:
            ready.set()
            return await PayrollService(db=session).close_period(
                month=3,
                year=2026,
                current_user=user,
                background_tasks=BackgroundTasks(),
            )

    async with factory() as writer:
        writer.add_all(punches(user.id, "2026-03-02"))
        await writer.flush()  # Holds the period lock, with uncommitted source rows.
        with patch.object(excel_service, "generate_excel_report", side_effect=generate):
            closing = asyncio.create_task(close())
            await ready.wait()
            await writer.commit()
            closure = await asyncio.wait_for(closing, timeout=10)
    assert closure.is_closed
    assert observed == [480]


@pytest.mark.asyncio
async def test_fractional_schedules_preserve_legacy_period_totals(pg_session_factory):
    factory = pg_session_factory
    user = await seed(factory)
    first, last = date(2026, 4, 1), date(2026, 4, 10)
    async with factory() as session:
        schedules = [
            UserWorkScheduleConfig(
                user_id=user.id,
                day_of_week=day,
                daily_hours=8.08,
                valid_from=first,
                valid_until=last,
            )
            for day in range(7)
        ]
        session.add_all(schedules)
        await session.commit()
    async with factory() as session:
        result = await daily_summary_service.build_period(
            session, user.id, first, last, [], [], [], schedules
        )
    legacy = time_calculation_service.calculate_period_time(
        first, last, [], [], [], schedules
    )
    assert result.total_expected_seconds == pytest.approx(legacy.total_expected_seconds)
    assert result.total_missing_seconds == pytest.approx(legacy.total_missing_seconds)
    assert round(result.total_expected_seconds / 60) == 4848


@pytest.mark.asyncio
async def test_restore_accepts_edited_parent_after_child_and_preserves_multiline_text(
    pg_session_factory, tmp_path
):
    factory = pg_session_factory
    async with factory() as session:
        names = (
            (
                await session.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables WHERE table_schema='public' "
                        "AND table_type='BASE TABLE' AND table_name<>'alembic_version'"
                    )
                )
            )
            .scalars()
            .all()
        )
    body = (
        "INSERT INTO users(id,username,role) VALUES(1,'synthetic','EMPLOYEE');\n"
        "INSERT INTO companies(id,name,cnpj,address) VALUES(1,'first\n\\restrict content\n\\network-path\nlast','synthetic','address');\n"
        "INSERT INTO time_records(id,user_id,record_type,record_datetime,original_record_id) "
        "VALUES(101,1,'ENTRY','2026-02-03T08:05:00-03:00',100);\n"
        "INSERT INTO time_records(id,user_id,record_type,record_datetime) VALUES(100,1,'ENTRY','2026-02-03T08:00:00-03:00');\n"
    )
    path = tmp_path / "restore.sql"
    path.write_text(body)
    counts = {name: 0 for name in names}
    counts.update(users=1, companies=1, time_records=2)
    add_manifest(path, counts)
    await asyncio.to_thread(apply_sql_file, path, allow_destructive=True)
    async with factory() as session:
        assert (
            await session.scalar(select(TimeRecord).where(TimeRecord.id == 101))
        ).original_record_id == 100
        value = await session.scalar(text("SELECT name FROM companies"))
        assert value == "first\n\\restrict content\n\\network-path\nlast"


@pytest.mark.asyncio
async def test_actual_asyncpg_duplicate_constraint_is_recognized(pg_session_factory):
    factory = pg_session_factory
    user = await seed(factory)
    async with factory() as session:
        await async_payroll_repository.create(
            session, month=1, year=2026, user_id=user.id
        )
    async with factory() as session:
        with pytest.raises(IntegrityError) as failure:
            await async_payroll_repository.create(
                session, month=1, year=2026, user_id=user.id
            )
        assert constraint_name(failure.value) == "uq_payroll_closures_active_period"
        await session.rollback()


def test_alembic_metadata_matches_migrated_schema(pg_url):
    subprocess.run([sys.executable, "-m", "alembic", "check"], check=True, timeout=30)


def test_sync_session_keeps_fortaleza_for_late_evening_records(pg_url):
    program = """
import json
from datetime import datetime
from sqlalchemy import select, text
from app.database.models import Base
from app.database.session import SessionLocal
from app.features.users.user_models import User
from app.features.time_records.time_record_models import TimeRecord
from app.features.daily_summaries.daily_summary_models import DailySummary
from app.shared.enums import UserRole, RecordType
with SessionLocal() as session:
    user = User(username="synthetic-sync", role=UserRole.EMPLOYEE)
    session.add(user)
    session.commit()
    session.add_all([
        TimeRecord(
            user_id=user.id, record_type=kind,
            record_datetime=datetime.fromisoformat(f"2026-02-02T{clock}:00-03:00")
        )
        for kind, clock in [(RecordType.ENTRY, "22:00"), (RecordType.EXIT, "23:00")]
    ])
    session.commit()
with SessionLocal() as session:
    row = session.scalar(select(DailySummary))
    first = session.scalar(select(TimeRecord).order_by(TimeRecord.record_datetime))
    print(json.dumps({
        "worked_minutes": float(row.worked_minutes),
        "first_record_day": first.record_datetime.date().isoformat(),
        "first_record_hour": first.record_datetime.hour,
        "session_timezone": session.scalar(text("SHOW timezone")),
    }))
"""
    result = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    values = json.loads(result.stdout)
    assert values == {
        "worked_minutes": 60,
        "first_record_day": "2026-02-02",
        "first_record_hour": 22,
        "session_timezone": "America/Fortaleza",
    }


@pytest.mark.asyncio
async def test_concurrent_writers_recalculate_the_complete_day(pg_session_factory):
    factory = pg_session_factory
    user = await seed(factory)
    async with factory() as session:
        session.add(punches(user.id)[0])
        await session.commit()
    async with factory() as morning, factory() as afternoon:
        morning.add(
            TimeRecord(
                user_id=user.id,
                record_type=RecordType.EXIT,
                record_datetime=datetime.fromisoformat("2026-02-02T12:00:00-03:00"),
            )
        )
        afternoon.add_all(
            [
                TimeRecord(
                    user_id=user.id,
                    record_type=kind,
                    record_datetime=datetime.fromisoformat(
                        f"2026-02-02T{clock}:00-03:00"
                    ),
                )
                for kind, clock in [
                    (RecordType.ENTRY, "13:00"),
                    (RecordType.EXIT, "17:00"),
                ]
            ]
        )
        await asyncio.wait_for(morning.flush(), timeout=10)
        await asyncio.wait_for(afternoon.flush(), timeout=10)
        await asyncio.wait_for(
            asyncio.gather(morning.commit(), afternoon.commit()), timeout=10
        )
    async with factory() as session:
        assert await session.scalar(select(func.count()).select_from(TimeRecord)) == 4
        assert (await session.scalar(select(DailySummary))).worked_minutes == 480


@pytest.mark.asyncio
async def test_encrypted_backup_roundtrip_preserves_values_and_summaries(
    pg_session_factory, tmp_path, monkeypatch
):
    factory = pg_session_factory
    user = await seed(factory)
    company_name = "first\n\\restrict user content\n\\unrestrict user content\n\\network-path\nlast"
    async with factory() as session:
        session.add(
            Company(name=company_name, cnpj="synthetic", address="Synthetic address")
        )
        session.add_all(punches(user.id))
        await session.commit()
        names = (
            (
                await session.execute(
                    text(
                        "SELECT table_name FROM information_schema.tables "
                        "WHERE table_schema='public' AND table_type='BASE TABLE' "
                        "AND table_name <> 'alembic_version'"
                    )
                )
            )
            .scalars()
            .all()
        )
        counts = {
            name: await session.scalar(text(f'SELECT COUNT(*) FROM "{name}"'))
            for name in names
        }
    service = BackupService()
    data = tmp_path / "backup.sql"
    assert await asyncio.to_thread(
        service._dump_postgresql_python,
        str(data),
        service._get_postgres_connection_params(),
    )
    add_manifest(data, counts)
    secret = "synthetic-test-secret-with-more-than-32-bytes"
    monkeypatch.setattr(settings, "SECRET_KEY", secret)
    monkeypatch.setenv("SECRET_KEY", secret)
    encrypted = await asyncio.to_thread(
        service.compress_files,
        {str(data): "spe_dump.sql"},
        str(tmp_path / "backup.zip"),
    )
    assert encrypted
    await asyncio.to_thread(restore_backup, Path(encrypted), allow_destructive=True)
    async with factory() as session:
        assert await session.scalar(select(Company.name)) == company_name
        assert (await session.scalar(select(DailySummary))).worked_minutes == 480
        assert await session.scalar(select(func.count()).select_from(TimeRecord)) == 2
        assert (
            await session.scalar(text("SELECT version_num FROM alembic_version"))
            == ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
        )


def test_alembic_connects_with_percent_encoded_password(pg_url, monkeypatch):
    import uuid

    url = make_url(pg_url)
    admin = psycopg2.connect(
        url.set(drivername="postgresql").render_as_string(hide_password=False)
    )
    admin.autocommit = True
    role = "spe_special_" + uuid.uuid4().hex
    password = "synthetic@%:password"
    try:
        with admin.cursor() as cursor:
            cursor.execute(
                sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                    sql.Identifier(role), sql.Literal(password)
                )
            )
            cursor.execute(
                sql.SQL("GRANT SELECT ON alembic_version TO {}").format(
                    sql.Identifier(role)
                )
            )
        monkeypatch.setenv(
            "SQLALCHEMY_DATABASE_URI",
            url.set(username=role, password=password).render_as_string(
                hide_password=False
            ),
        )
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "current"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        assert ScriptDirectory.from_config(Config("alembic.ini")).get_current_head() in result.stdout
    finally:
        with admin.cursor() as cursor:
            cursor.execute(
                sql.SQL("REVOKE SELECT ON alembic_version FROM {}").format(
                    sql.Identifier(role)
                )
            )
            cursor.execute(sql.SQL("DROP ROLE {}").format(sql.Identifier(role)))
        admin.close()
