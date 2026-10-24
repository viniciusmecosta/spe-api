import asyncio
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select, text, update

from app.features.system import job_queue
from app.features.system.delivery_result import DeliveryResult
from app.features.system.system_models import BackgroundJob, RoutineLog

pytestmark = pytest.mark.asyncio


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
