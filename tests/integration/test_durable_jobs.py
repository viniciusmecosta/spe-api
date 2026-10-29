import asyncio
from datetime import date, timedelta
from unittest.mock import AsyncMock

from sqlalchemy import select, text, update

import pytest
from app.core.config import settings
from app.features.system import job_queue
from app.features.system.delivery_result import DeliveryResult
from app.features.system.system_models import BackgroundJob, RoutineLog

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def enable_test_worker(monkeypatch, prevent_real_email_sending):
    monkeypatch.setattr(settings, 'BACKGROUND_JOBS_ENABLED', True)


async def expire(factory, job_id):
    async with factory() as session:
        job = await session.get(BackgroundJob, job_id)
        result = dict(job.result)
        if 'parts' in result:
            result['parts'] = [{**item, 'retry_at': 0} for item in result['parts']]
            job.result = result
        await session.execute(update(BackgroundJob).where(BackgroundJob.id == job_id).values(
            next_attempt_at=job_queue.utc_now() - timedelta(seconds=1),
            lease_until=job_queue.utc_now() - timedelta(seconds=1)))
        await session.commit()


async def ready_job(factory, parts, key=None):
    async with factory() as session:
        job = await job_queue.enqueue(session, 'NOTIFICATION', {'routine_type': 'TEST_DELIVERY'}, key)
        job.result = {'context': {}, 'parts': parts}
        await session.commit()
        return job.id


def part(status='PENDING'):
    return {'kind': 'text', 'text': 'Relatório', 'status': status, 'attempts': 0}


async def test_enqueue_deduplicates_and_claims_have_exclusive_lease(pg_session_factory):
    factory = pg_session_factory
    job_id = await ready_job(factory, [part()], 'same-period')
    async with factory() as session:
        duplicate = await job_queue.enqueue(session, 'NOTIFICATION', {}, 'same-period')
        assert duplicate.id == job_id
    claims = await asyncio.gather(job_queue.claim(), job_queue.claim())
    assert sum(item is not None for item in claims) == 1
    first = next(item for item in claims if item)
    await expire(factory, job_id)
    replacement = await job_queue.claim()
    assert replacement['token'] != first['token']
    assert not await job_queue.checkpoint(first, 'SUCCESS')
    assert await job_queue.checkpoint(replacement, 'FAILED')


async def test_retry_is_persisted_without_resending_successful_parts(pg_session_factory, mocker):
    factory = pg_session_factory
    job_id = await ready_job(factory, [part(), part()])
    deliver = mocker.patch('app.features.system.notification_jobs._deliver', new_callable=AsyncMock,
                          side_effect=[DeliveryResult('SUCCESS'), DeliveryResult('RETRY', retry_after=30), DeliveryResult('SUCCESS')])
    await job_queue.process_once()
    async with factory() as session:
        job = await session.get(BackgroundJob, job_id)
        assert job.status == 'RETRY'
        assert [item['status'] for item in job.result['parts']] == ['SUCCESS', 'RETRY']
    await expire(factory, job_id)
    await job_queue.process_once()
    async with factory() as session:
        job = await session.get(BackgroundJob, job_id)
        assert job.status == 'SUCCESS'
        assert [item['attempts'] for item in job.result['parts']] == [1, 2]
        assert await session.scalar(select(RoutineLog.status)) == 'SUCCESS'
    assert deliver.await_count == 3


async def test_restart_preserves_uncertain_part_and_delivers_remaining_parts(pg_session_factory, mocker):
    factory = pg_session_factory
    job_id = await ready_job(factory, [part('SENDING'), part()])
    deliver = mocker.patch('app.features.system.notification_jobs._deliver', new_callable=AsyncMock,
                          return_value=DeliveryResult('SUCCESS'))
    await job_queue.process_once()
    async with factory() as session:
        job = await session.get(BackgroundJob, job_id)
        assert job.status == 'PARTIAL'
        assert [item['status'] for item in job.result['parts']] == ['UNCERTAIN', 'SUCCESS']
        assert (await session.scalar(select(RoutineLog))).status == 'PARTIAL'
    deliver.assert_awaited_once()


async def test_attachment_failure_is_recorded_as_partial(pg_session_factory, mocker):
    factory = pg_session_factory
    job_id = await ready_job(factory, [part(), {'kind': 'document', 'path': 'missing', 'filename': 'log.log',
                                               'caption': 'Log', 'status': 'PENDING', 'attempts': 0}])
    mocker.patch('app.features.system.notification_jobs._deliver', new_callable=AsyncMock,
                 side_effect=[DeliveryResult('SUCCESS'), DeliveryResult('FAILED', 'Arquivo ausente')])
    await job_queue.process_once()
    async with factory() as session:
        job = await session.get(BackgroundJob, job_id)
        assert job.status == 'PARTIAL'
        assert job.result['summary']['FAILED'] == 1
        assert job.result['parts'][1]['detail'] == 'Arquivo ausente'


async def test_reprocess_resumes_from_committed_cursor_after_interruption(pg_session_factory, mocker):
    factory = pg_session_factory
    async with factory() as session:
        job = await job_queue.enqueue(session, 'REPROCESS', {
            'user_ids': [123], 'start_date': '2026-10-01', 'end_date': '2026-10-03',
            'routine_type': 'DAILY_SUMMARIES_REPROCESS'})
        await session.commit()
        job_id = job.id
    recalculate = mocker.patch('app.features.daily_summaries.daily_summary_reprocess_service.recalculate_changed_days',
                               new_callable=AsyncMock, side_effect=[True, asyncio.CancelledError()])
    with pytest.raises(asyncio.CancelledError):
        await job_queue.process_once()
    async with factory() as session:
        assert (await session.get(BackgroundJob, job_id)).result['cursor'] == 1
    await expire(factory, job_id)
    recalculate.side_effect = None
    recalculate.return_value = True
    await job_queue.process_once()
    async with factory() as session:
        job = await session.get(BackgroundJob, job_id)
        assert job.status == 'SUCCESS'
        assert job.result['summary'] == {'total': 3, 'completed': 3, 'processed': 3, 'failed': 0}
    assert recalculate.await_args_list[-2].args == ({(123, date(2026, 10, 2))},)


async def test_private_attachment_survives_original_cleanup_and_is_redacted(pg_session_factory, tmp_path):
    from app.features.system.notification_jobs import _retain_file
    source = tmp_path / 'source.log'
    source.write_text('ERROR https://api.telegram.org/bot123:secret/sendDocument password=secret')
    path, filename = _retain_file(42, str(source), 'system.log')
    source.unlink()
    from pathlib import Path
    retained = Path(path)
    assert retained.is_file()
    assert '123:secret' not in retained.read_text()
    assert 'password=secret' not in retained.read_text()
    assert 'public' not in retained.parts


async def seed_notification_data(factory, tmp_path):
    from datetime import datetime
    from PIL import Image
    from app.features.companies.company_models import Company
    from app.features.time_records.time_record_models import TimeRecord
    from app.features.users.user_models import User
    from app.shared.enums import RecordType, UserRole
    async with factory() as session:
        manager = User(username='notification-admin', name='Responsável', email='responsavel@example.test',
                       role=UserRole.MAINTAINER)
        employee = User(username='notification-user', name='Ana <Nevoa>', role=UserRole.EMPLOYEE)
        session.add_all([manager, employee, Company(name='Empresa Dinâmica', cnpj='synthetic', address='Rua Exemplo',
                                                    logo_path='logo.png')])
        await session.commit()
        session.add_all([TimeRecord(user_id=employee.id, record_type=kind,
                                    record_datetime=datetime.fromisoformat(f'2026-10-23T{hour}:00-03:00'))
                         for kind, hour in ((RecordType.ENTRY, '07:00'), (RecordType.EXIT, '16:00'))])
        await session.commit()
    Image.new('RGB', (100, 30), color='green').save(tmp_path / 'logo.png')


@pytest.mark.parametrize('routine', ['EMAIL_DAILY_BACKUP', 'TELEGRAM_DAILY_REPORT', 'TELEGRAM_MANUAL_REPORT',
                                     'TELEGRAM_HOURLY_BACKUP', 'TELEGRAM_MANUAL_BACKUP', 'EMAIL_PAYROLL'])
async def test_notification_preparation_preserves_files_and_real_report_content(pg_session_factory, tmp_path, mocker,
                                                                                routine):
    from app.features.system.email_service import email_service
    from app.features.system.telegram_service import telegram_service
    from app.features.system.routine_orchestrator import routine_orchestrator
    factory = pg_session_factory
    await seed_notification_data(factory, tmp_path)
    log = tmp_path / 'day.log'
    log.write_text('07:00:00 [ERROR] https://api.telegram.org/bot123:exposed/sendDocument password=hidden')
    mocker.patch('app.features.system.notification_jobs.get_log_path', return_value=str(log))
    mocker.patch('app.features.system.routine_orchestrator.get_log_path', return_value=str(log))
    archive = tmp_path / 'backup.zip.enc'
    archive.write_bytes(b'encrypted synthetic backup')
    schema, data = tmp_path / 'schema.sql', tmp_path / 'data.sql'
    schema.write_text('synthetic schema')
    data.write_text('synthetic rows')
    mocker.patch.object(routine_orchestrator, '_generate_backup_files_zip', new_callable=AsyncMock,
                        return_value=(str(schema), str(data), str(archive)))
    smtp = mocker.patch.object(email_service, '_send_message', return_value=DeliveryResult('SUCCESS'))
    text_send = mocker.patch.object(telegram_service, 'deliver_text', return_value=DeliveryResult('SUCCESS'))
    document_send = mocker.patch.object(telegram_service, 'deliver_document', return_value=DeliveryResult('SUCCESS'))
    payload = {'routine_type': routine, 'start_date': '2026-10-23', 'end_date': '2026-10-23',
               'target_date': '2026-10-23'}
    if routine == 'EMAIL_PAYROLL':
        reports = tmp_path / 'reports'
        reports.mkdir()
        (reports / 'payroll.xlsx').write_bytes(b'synthetic workbook')
        payload.update(action='Fechamento', month=10, year=2026, user_name='Responsável',
                       report_path='reports/payroll.xlsx', to_emails=['responsavel@example.test'])
    job_id = await job_queue.submit('NOTIFICATION', payload)
    await job_queue.process_once()
    async with factory() as session:
        job = await session.get(BackgroundJob, job_id)
        assert job.status == 'SUCCESS'
        assert job.result['context']['company'] == 'Empresa Dinâmica'
        if routine.startswith('EMAIL'):
            message = smtp.call_args.args[0]
            body = next(part.get_payload(decode=True).decode('utf-8') for part in message.walk() if
                        part.get_content_type() == 'text/html')
            assert 'Empresa Dinâmica' in body
            assert 'cid:company-logo' in body
            if routine == 'EMAIL_DAILY_BACKUP':
                assert 'Ana &lt;Nevoa&gt;' in body
                assert '07:00' in body and '16:00' in body
                assert 'Ocorrências relevantes' in body
                assert '123:exposed' not in body
                assert 'password=hidden' not in body
        elif 'REPORT' in routine:
            assert 'Ana &lt;Nevoa&gt;' in text_send.call_args.args[0]
            assert 'E: 07:00' in text_send.call_args.args[0]
        if routine == 'TELEGRAM_HOURLY_BACKUP':
            document_send.assert_called_once()
    if 'BACKUP' in routine:
        assert not archive.exists()
    for retained_log in (tmp_path / '.delivery_queue' / str(job_id)).glob('*.log'):
        assert '123:exposed' not in retained_log.read_text()
        assert 'password=hidden' not in retained_log.read_text()


async def test_generation_failure_persists_retries_and_final_failure(pg_session_factory, mocker):
    factory = pg_session_factory
    mocker.patch('app.features.system.notification_jobs.prepare_notification', new_callable=AsyncMock,
                 side_effect=RuntimeError('synthetic failure'))
    job_id = await job_queue.submit('NOTIFICATION', {'routine_type': 'SYNTHETIC_FAILURE'})
    for attempt in range(1, 5):
        await job_queue.process_once()
        async with factory() as session:
            job = await session.get(BackgroundJob, job_id)
            assert job.attempts == attempt
            assert job.status == ('FAILED' if attempt == 4 else 'RETRY')
        await expire(factory, job_id)
    async with factory() as session:
        logs = list((await session.scalars(select(RoutineLog))).all())
        assert len(logs) == 1
        assert logs[0].status == 'FAILED'


async def test_long_delivery_renews_lease_without_allowing_a_second_worker(pg_session_factory, monkeypatch, mocker):
    monkeypatch.setattr(job_queue, 'LEASE_SECONDS', 0.6)
    started = asyncio.Event()
    release = asyncio.Event()

    async def deliver(*args):
        started.set()
        await release.wait()
        return DeliveryResult('SUCCESS')

    mocker.patch('app.features.system.notification_jobs._deliver', side_effect=deliver)
    job_id = await ready_job(pg_session_factory, [part()])
    worker = asyncio.create_task(job_queue.process_once())
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        await asyncio.sleep(0.9)
        assert await job_queue.claim() is None
    finally:
        release.set()
        await worker
    async with pg_session_factory() as session:
        assert (await session.get(BackgroundJob, job_id)).status == 'SUCCESS'


async def test_success_cleans_only_confirmed_attachments_and_scheduled_cleanup_recovers_leftovers(
        pg_session_factory, tmp_path, mocker):
    from app.features.system.notification_jobs import cleanup_delivered_attachments

    root = tmp_path / '.delivery_queue'
    job_id = await ready_job(pg_session_factory, [part()])
    directory = root / str(job_id)
    directory.mkdir(parents=True)
    (directory / 'report.log').write_text('synthetic report')
    mocker.patch('app.features.system.notification_jobs._deliver', return_value=DeliveryResult('SUCCESS'))
    await job_queue.process_once()
    assert not directory.exists()
    directory.mkdir()
    (directory / 'leftover.log').write_text('interrupted cleanup')
    retained = {}
    async with pg_session_factory() as session:
        for status in ('PENDING', 'RETRY', 'FAILED', 'PARTIAL', 'UNCERTAIN'):
            job = await job_queue.enqueue(session, 'NOTIFICATION', {})
            job.status = status
            path = root / str(job.id)
            path.mkdir()
            (path / 'pending.log').write_text(status)
            retained[status] = path
        await session.commit()
    await cleanup_delivered_attachments()
    assert not directory.exists()
    assert all((path / 'pending.log').read_text() == status for status, path in retained.items())


async def test_disabled_worker_does_not_claim_queued_work(pg_session_factory, monkeypatch):
    from app.core.config import settings
    job_id = await ready_job(pg_session_factory, [part()])
    monkeypatch.setattr(settings, 'BACKGROUND_JOBS_ENABLED', False)
    await job_queue.process_once()
    async with pg_session_factory() as session:
        job = await session.get(BackgroundJob, job_id)
        assert job.status == 'PENDING'
        assert job.attempts == 0


async def test_lease_renewal_accepts_its_completed_job_but_rejects_another_owner(pg_session_factory, monkeypatch):
    monkeypatch.setattr(job_queue, 'LEASE_SECONDS', 0.03)
    job_id = await ready_job(pg_session_factory, [part()])
    first = await job_queue.claim()
    await expire(pg_session_factory, job_id)
    second = await job_queue.claim()
    with pytest.raises(RuntimeError, match='reserva'):
        await job_queue.keep_lease(first)
    assert await job_queue.checkpoint(second, 'SUCCESS')
    await job_queue.keep_lease(second)


async def test_heartbeat_failure_cancels_delivery_and_preserves_uncertain_state(pg_session_factory, mocker):
    started, stopped = asyncio.Event(), asyncio.Event()

    async def deliver(*args):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()

    async def heartbeat(*args):
        await started.wait()
        raise RuntimeError('synthetic lease failure')

    delivery = mocker.patch('app.features.system.notification_jobs._deliver', side_effect=deliver)
    lease = mocker.patch.object(job_queue, 'keep_lease', side_effect=heartbeat)
    job_id = await ready_job(pg_session_factory, [part()])
    await asyncio.wait_for(job_queue.process_once(), timeout=5)
    assert stopped.is_set()
    async with pg_session_factory() as session:
        job = await session.get(BackgroundJob, job_id)
        assert job.status == 'RETRY'
        assert job.result['parts'][0]['status'] == 'SENDING'
    await expire(pg_session_factory, job_id)
    lease.side_effect = None
    await asyncio.wait_for(job_queue.process_once(), timeout=5)
    async with pg_session_factory() as session:
        assert (await session.get(BackgroundJob, job_id)).status == 'UNCERTAIN'
    delivery.assert_awaited_once()
