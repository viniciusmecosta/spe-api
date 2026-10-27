from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import settings
from app.features.system import notification_jobs
from app.features.system.delivery_result import DeliveryResult
from app.features.users.user_models import User
from app.shared.enums import UserRole


def _ctx(session):
    class _Manager:
        async def __aenter__(self):
            return session

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            return False

    return _Manager()


@pytest.mark.asyncio
async def test_remove_and_cleanup_delivered_attachments(mocker, tmp_path):
    mocker.patch.object(settings, "UPLOAD_DIR", str(tmp_path))

    notification_jobs._remove_delivered_files(999)

    job_dir = tmp_path / notification_jobs.DELIVERY_DIRECTORY / "12"
    job_dir.mkdir(parents=True)
    (job_dir / "file.txt").write_text("hello")

    mocker.patch("app.features.system.notification_jobs.shutil.rmtree", side_effect=OSError("busy"))
    notification_jobs._remove_delivered_files(12)
    assert job_dir.exists()

    mocker.stopall()
    mocker.patch.object(settings, "UPLOAD_DIR", str(tmp_path))

    session = MagicMock()
    scalars_res = MagicMock()
    scalars_res.all.return_value = [12]
    session.scalars = AsyncMock(return_value=scalars_res)
    mocker.patch("app.features.system.notification_jobs.get_async_session_context", return_value=_ctx(session))

    await notification_jobs.cleanup_delivered_attachments()
    assert not job_dir.exists()

    shutil_rm = tmp_path / notification_jobs.DELIVERY_DIRECTORY
    shutil_rm.rmdir()
    await notification_jobs.cleanup_delivered_attachments()


def test_retain_file_and_log_incidents(mocker, tmp_path):
    mocker.patch.object(settings, "UPLOAD_DIR", str(tmp_path))
    src_log = tmp_path / "app.log"
    lines = [f"[ERROR] line {i}" for i in range(12)] + ["[INFO] normal"]
    src_log.write_text("\n".join(lines), encoding="utf-8")

    src_bin = tmp_path / "data.bin"
    src_bin.write_bytes(b"binary")

    retained_log = notification_jobs._retain_file(1, str(src_log), "app.log")
    retained_bin = notification_jobs._retain_file(1, str(src_bin), "data.bin")

    incidents = notification_jobs._log_incidents([retained_log, retained_bin])
    assert len(incidents) == 11
    assert "Mais 2 ocorrências" in incidents[-1]

    incidents_short = notification_jobs._log_incidents([(str(src_bin), "data.bin")])
    assert incidents_short == []


@pytest.mark.asyncio
async def test_prepare_payroll_and_report_content(mocker, tmp_path):
    mocker.patch.object(settings, "UPLOAD_DIR", str(tmp_path))
    session = MagicMock()
    mocker.patch("app.features.system.notification_jobs.get_async_session_context", return_value=_ctx(session))
    mocker.patch(
        "app.features.system.notification_jobs.company_context",
        new_callable=AsyncMock,
        return_value={"project": "SPE", "version": "1.0", "environment": "prod", "generated_at": "01/01/2026 10:00"},
    )

    rep_dir = tmp_path / "reports"
    rep_dir.mkdir()
    rep_file = rep_dir / "folha.xlsx"
    rep_file.write_bytes(b"xlsx")

    job = {
        "id": 10,
        "payload": {
            "routine_type": "EMAIL_PAYROLL",
            "action": "Fechamento",
            "user_name": "Admin",
            "month": 5,
            "year": 2026,
            "report_path": "reports/folha.xlsx",
            "to_emails": ["a@a.com"],
        },
    }
    prepared = await notification_jobs.prepare_notification(job)
    assert len(prepared["parts"]) == 1
    assert prepared["parts"][0]["kind"] == "email"

    job_bad_path = {
        "id": 11,
        "payload": {**job["payload"], "report_path": "../outside.xlsx"},
    }
    with pytest.raises(ValueError, match="inválido"):
        await notification_jobs._prepare_payroll(job_bad_path)

    job_no_emails = {
        "id": 12,
        "payload": {**job["payload"], "report_path": None, "to_emails": []},
    }
    with pytest.raises(ValueError, match="Nenhum responsável"):
        await notification_jobs._prepare_payroll(job_no_emails)


@pytest.mark.asyncio
async def test_prepare_notification_email_and_telegram_branches(mocker, tmp_path):
    mocker.patch.object(settings, "UPLOAD_DIR", str(tmp_path))
    log_file = tmp_path / "sys.log"
    log_file.write_text("[INFO] ok", encoding="utf-8")

    session = MagicMock()
    mocker.patch("app.features.system.notification_jobs.get_async_session_context", return_value=_ctx(session))
    mocker.patch(
        "app.features.system.notification_jobs.company_context",
        new_callable=AsyncMock,
        return_value={"project": "SPE", "version": "1.0", "environment": "prod", "generated_at": "01/01/2026 10:00"},
    )
    mocker.patch(
        "app.features.system.notification_jobs.async_routine_log_repository.get_last_successful_target_date",
        new_callable=AsyncMock,
        return_value=date(2026, 8, 1),
    )
    mocker.patch("app.features.system.notification_jobs.get_log_path", return_value=str(log_file))

    from app.features.system.routine_orchestrator import routine_orchestrator

    mocker.patch.object(
        routine_orchestrator,
        "_generate_daily_backup_report",
        new_callable=AsyncMock,
        return_value=("<p>rel</p>", [], "Período"),
    )

    scalars_empty = MagicMock()
    scalars_empty.all.return_value = []
    session.scalars = AsyncMock(return_value=scalars_empty)
    with pytest.raises(ValueError, match="Nenhum responsável"):
        await notification_jobs.prepare_notification(
            {
                "id": 20,
                "payload": {
                    "routine_type": "EMAIL_DAILY_BACKUP",
                    "start_date": "2026-08-02",
                    "end_date": "2026-08-02",
                },
            }
        )

    maint = User(id=1, role=UserRole.MAINTAINER, is_active=True, email="m@m.com")
    scalars_maint = MagicMock()
    scalars_maint.all.return_value = [maint]
    session.scalars = AsyncMock(return_value=scalars_maint)

    mocker.patch.object(
        routine_orchestrator,
        "_generate_backup_files_zip",
        new_callable=AsyncMock,
        return_value=(None, None, None),
    )
    with pytest.raises(RuntimeError, match="backup criptografado"):
        await notification_jobs._retain_backup(21)

    archive_file = tmp_path / "spe.zip.enc"
    archive_file.write_bytes(b"enc")
    mocker.patch.object(
        routine_orchestrator,
        "_generate_backup_files_zip",
        new_callable=AsyncMock,
        return_value=("b", "s", str(archive_file)),
    )
    mocker.patch.object(routine_orchestrator, "_cleanup_backup_files", new_callable=AsyncMock)

    email_job = {
        "id": 22,
        "payload": {
            "routine_type": "EMAIL_DAILY_BACKUP",
            "start_date": "2026-08-02",
            "end_date": "2026-08-02",
        },
    }
    prepared_email = await notification_jobs.prepare_notification(email_job)
    assert prepared_email["parts"][0]["kind"] == "email"

    mocker.patch(
        "app.features.system.notification_jobs.telegram_service.generate_report_text",
        new_callable=AsyncMock,
        return_value="Relatório",
    )
    tg_report_job = {
        "id": 23,
        "payload": {
            "routine_type": "TELEGRAM_MANUAL_REPORT",
            "start_date": "2026-08-02",
            "end_date": "2026-08-02",
        },
    }
    prepared_tg = await notification_jobs.prepare_notification(tg_report_job)
    assert any(p["kind"] == "text" for p in prepared_tg["parts"])

    tg_hourly_job = {
        "id": 24,
        "payload": {
            "routine_type": "TELEGRAM_HOURLY_BACKUP",
            "start_date": "2026-08-02",
            "end_date": "2026-08-02",
        },
    }
    prepared_hourly = await notification_jobs.prepare_notification(tg_hourly_job)
    assert any(p["kind"] == "document" for p in prepared_hourly["parts"])


@pytest.mark.asyncio
async def test_deliver_and_process_notification_job(mocker, tmp_path):
    mocker.patch.object(settings, "UPLOAD_DIR", str(tmp_path))
    mocker.patch(
        "app.features.system.notification_jobs.telegram_service.deliver_text",
        return_value=DeliveryResult("SUCCESS"),
    )
    mocker.patch(
        "app.features.system.notification_jobs.telegram_service.deliver_document",
        return_value=DeliveryResult("RETRY", "rate", 5),
    )
    mocker.patch(
        "app.features.system.notification_jobs.email_service.deliver_email",
        return_value=DeliveryResult("RETRY", "temp", 0),
    )

    assert (await notification_jobs._deliver({"kind": "text", "text": "hi"}, {})).status == "SUCCESS"
    assert (
        await notification_jobs._deliver(
            {"kind": "document", "path": "p", "caption": "c", "filename": "f"}, {}
        )
    ).status == "RETRY"
    assert (
        await notification_jobs._deliver(
            {
                "kind": "email",
                "to": ["a@a.com"],
                "attachments": [],
                "report_html": "<p>h</p>",
                "period": "p",
                "attempts": 1,
                "message_id": "<1>",
            },
            {},
        )
    ).status == "RETRY"

    assert notification_jobs._batch_status([{"status": "SUCCESS"}], {"SUCCESS": 1, "PARTIAL": 0, "UNCERTAIN": 0}) == "SUCCESS"
    assert notification_jobs._batch_status([{"status": "PARTIAL"}], {"SUCCESS": 0, "PARTIAL": 1, "UNCERTAIN": 0}) == "PARTIAL"
    assert notification_jobs._batch_status([{"status": "UNCERTAIN"}], {"SUCCESS": 0, "PARTIAL": 0, "UNCERTAIN": 1}) == "UNCERTAIN"
    assert notification_jobs._batch_status([{"status": "FAILED"}], {"SUCCESS": 0, "PARTIAL": 0, "UNCERTAIN": 0}) == "FAILED"

    mocker.patch(
        "app.features.system.notification_jobs.prepare_notification",
        new_callable=AsyncMock,
        return_value={"parts": [{"kind": "text", "text": "t", "status": "PENDING", "attempts": 0}], "context": {}},
    )
    mocker.patch("app.features.system.notification_jobs.checkpoint", new_callable=AsyncMock, return_value=False)
    await notification_jobs.process_notification_job({"id": 1, "result": {}})

    mocker.patch("app.features.system.notification_jobs.checkpoint", new_callable=AsyncMock, side_effect=[True, False])
    await notification_jobs.process_notification_job({"id": 2, "result": {}})

    mocker.patch("app.features.system.notification_jobs.checkpoint", new_callable=AsyncMock, return_value=True)
    job_retry = {
        "id": 3,
        "result": {
            "context": {},
            "parts": [
                {"kind": "SENDING_TEST", "status": "SENDING", "attempts": 1},
                {"kind": "document", "path": "p", "caption": "c", "filename": "f", "status": "PENDING", "attempts": 0},
                {"kind": "email", "to": ["a@a.com"], "attachments": [], "report_html": "", "period": "", "message_id": "<1>", "status": "RETRY", "attempts": 3, "retry_at": 0},
            ],
        },
    }
    await notification_jobs.process_notification_job(job_retry)
    assert job_retry["result"]["parts"][0]["status"] == "UNCERTAIN"
    assert job_retry["result"]["parts"][1]["status"] == "RETRY"
    assert job_retry["result"]["parts"][2]["status"] == "FAILED"

    job_success = {
        "id": 4,
        "result": {
            "context": {},
            "parts": [{"kind": "text", "text": "ok", "status": "PENDING", "attempts": 0}],
        },
    }
    await notification_jobs.process_notification_job(job_success)
    assert job_success["result"]["parts"][0]["status"] == "SUCCESS"
