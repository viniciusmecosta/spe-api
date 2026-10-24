from zoneinfo import ZoneInfo
import asyncio
import copy
import html
import shutil
import secrets
import uuid
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select

from app.core.config import settings
from app.core.logger import get_log_path
from app.core.redaction import redact
from app.database.session import get_async_session_context
from app.features.system.delivery_result import DeliveryResult
from app.features.system.email_service import email_service
from app.features.system.job_queue import checkpoint, utc_now
from app.features.system.notification_context import company_context
from app.features.system.system_repository import async_routine_log_repository
from app.features.system.telegram_service import telegram_service
from app.features.users.user_models import User
from app.shared.enums import UserRole


def _retain_file(job_id: int, source: str, filename: str) -> tuple[str, str]:
    directory = Path(settings.UPLOAD_DIR) / '.delivery_queue' / str(job_id)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = directory / (uuid.uuid4().hex + Path(filename).suffix)
    if filename.endswith('.log'):
        destination.write_text(redact(Path(source).read_text(encoding='utf-8', errors='replace')), encoding='utf-8')
    else:
        shutil.copyfile(source, destination)
    destination.chmod(0o600)
    return str(destination), filename


def _log_incidents(attachments) -> list[str]:
    incidents = []
    for path, filename in attachments:
        if not filename.endswith('.log'):
            continue
        for line in Path(path).read_text(encoding='utf-8', errors='replace').splitlines():
            if any(level in line for level in ('[ERROR]', '[CRIT]', '[CRITICAL]')):
                incidents.append(f'{filename}: {redact(line[:500])}')
    if len(incidents) > 10:
        return incidents[:10] + [f'Mais {len(incidents) - 10} ocorrências nos logs anexos.']
    return incidents


async def _prepare_payroll(job: dict) -> dict:
    from app.features.reports.template_service import template_service
    payload = job['payload']
    async with get_async_session_context() as session:
        context = await company_context(session)
    context.update(execution_id=str(job['id']), title='Folha de ponto')
    body = template_service.get_payroll_email_html(payload['action'], payload['user_name'],
               payload['month'], payload['year'], context['generated_at'])
    attachments = []
    if payload.get('report_path'):
        root = Path(settings.UPLOAD_DIR).resolve()
        report = (root / payload['report_path']).resolve()
        if not report.is_relative_to(root):
            raise ValueError('Caminho do relatório inválido')
        attachments.append(await asyncio.to_thread(_retain_file, job['id'], str(report), report.name))
    parts = [{'kind': 'email', 'to': [recipient], 'attachments': attachments,
              'report_html': body, 'period': f"Competência {payload['month']:02d}/{payload['year']}",
              'message_id': f'<{uuid.uuid4().hex}@spe.local>', 'status': 'PENDING', 'attempts': 0}
             for recipient in dict.fromkeys(payload['to_emails'])]
    if not parts:
        raise ValueError('Nenhum responsável com e-mail cadastrado')
    return {'parts': parts, 'context': context}


async def _report_content(session, routine, start, end, context):
    from app.features.system.routine_orchestrator import routine_orchestrator
    content = {'html': '', 'text': '', 'attachments': [], 'period': '', 'recipients': []}
    if 'REPORT' in routine and 'TELEGRAM' in routine:
        content['text'] = await telegram_service.generate_report_text(session, start, end)
        content['text'] += f"\n\n{html.escape(context.get('company', context['project']))} · {html.escape(context['version'])} · {html.escape(context['environment'])}\nExecução #{context['execution_id']}"
    if 'EMAIL' in routine:
        content['html'], content['attachments'], content['period'] = await routine_orchestrator._generate_daily_backup_report(session, start, end)
        users = (await session.scalars(select(User).where(User.role == UserRole.MAINTAINER,
                                  User.is_active.is_(True), User.email.isnot(None)).order_by(User.id))).all()
        content['recipients'] = [user.email for user in users if user.email]
        if not content['recipients']:
            raise ValueError('Nenhum responsável com e-mail cadastrado')
    return content


def _append_logs(attachments, routine, start, end):
    if routine == 'TELEGRAM_HOURLY_BACKUP':
        return
    log_end = end
    if routine != 'TELEGRAM_MANUAL_REPORT':
        log_end = max(end, utc_now().astimezone(ZoneInfo(settings.TIMEZONE)).date())
    existing_paths = {path for path, _ in attachments}
    log_day = start
    while log_day <= log_end:
        path = get_log_path(log_day)
        if Path(path).is_file() and path not in existing_paths:
            attachments.append((path, f'log_{log_day:%d%m%Y}.log'))
            existing_paths.add(path)
        log_day += timedelta(days=1)


async def _retain_backup(job_id):
    from app.features.system.routine_orchestrator import routine_orchestrator
    backup, sql, archive = await routine_orchestrator._generate_backup_files_zip()
    if not archive:
        raise RuntimeError('Não foi possível gerar o backup criptografado')
    try:
        return await asyncio.to_thread(_retain_file, job_id, archive, 'spe.zip.enc')
    finally:
        await routine_orchestrator._cleanup_backup_files(backup, sql, archive)


def _notification_parts(routine, content, attachments, context, start, end):
    if 'EMAIL' in routine:
        return [{'kind': 'email', 'to': [recipient], 'attachments': attachments,
                 'report_html': content['html'], 'period': content['period'],
                 'message_id': f'<{uuid.uuid4().hex}@spe.local>'}
                for recipient in dict.fromkeys(content['recipients'])]
    parts = []
    if content['text']:
        parts.extend({'kind': 'text', 'text': chunk} for chunk in telegram_service.split_text(content['text']))
    parts.extend({'kind': 'document', 'path': path, 'filename': filename,
                  'caption': f"{context.get('company', context['project'])} · {filename}\n{start:%d/%m/%Y} a {end:%d/%m/%Y} · Execução #{context['execution_id']}"}
                 for path, filename in attachments)
    return parts


async def prepare_notification(job: dict) -> dict:
    payload = job['payload']
    routine = payload['routine_type']
    if routine == 'EMAIL_PAYROLL':
        return await _prepare_payroll(job)
    end = date.fromisoformat(payload['end_date'])
    start = date.fromisoformat(payload['start_date'])
    async with get_async_session_context() as session:
        context = await company_context(session)
        context['execution_id'] = str(job['id'])
        if routine in ('EMAIL_DAILY_BACKUP', 'TELEGRAM_DAILY_REPORT'):
            last = await async_routine_log_repository.get_last_successful_target_date(session, routine)
            start = min(last + timedelta(days=1), end) if last else start
        content = await _report_content(session, routine, start, end, context)
    attachments = content['attachments']
    await asyncio.to_thread(_append_logs, attachments, routine, start, end)
    context['incidents'] = await asyncio.to_thread(_log_incidents, attachments)
    retained = [await asyncio.to_thread(_retain_file, job['id'], path, filename) for path, filename in attachments]
    if 'BACKUP' in routine:
        retained.insert(0, await _retain_backup(job['id']))
    parts = _notification_parts(routine, content, retained, context, start, end)
    for part in parts:
        part.update(status='PENDING', attempts=0)
    return {'parts': parts, 'context': context}


async def _deliver(part: dict, context: dict) -> DeliveryResult:
    if part['kind'] == 'text':
        return await asyncio.to_thread(telegram_service.deliver_text, part['text'])
    if part['kind'] == 'document':
        return await asyncio.to_thread(telegram_service.deliver_document, part['path'], part['caption'], part['filename'])
    info = {**context, 'attempt': part['attempts'], 'message_id': part['message_id']}
    return await asyncio.to_thread(email_service.deliver_email, part['to'], part['attachments'],
                                   part['report_html'], part['period'], info)


async def _process_part(job: dict, part: dict, now: float) -> bool:
    if part['status'] == 'SENDING':
        part.update(status='UNCERTAIN', detail='Serviço interrompido durante envio; conferir entrega')
    if part['status'] not in ('PENDING', 'RETRY') or part.get('retry_at', 0) > now:
        return True
    part['status'] = 'SENDING'
    part['attempts'] += 1
    if not await checkpoint(job):
        return False
    outcome = await _deliver(copy.deepcopy(part), job['result']['context'])
    status = outcome.status
    if status == 'RETRY' and part['attempts'] >= 4:
        status = 'FAILED'
    part.update(status=status, detail=redact(outcome.detail))
    if status == 'RETRY':
        part['retry_at'] = utc_now().timestamp() + (outcome.retry_after or min(300, 5 * 2 ** part['attempts'] + secrets.randbelow(6)))
    return await checkpoint(job)


def _batch_status(parts: list, counts: dict) -> str:
    if parts and counts['SUCCESS'] == len(parts):
        return 'SUCCESS'
    if counts['SUCCESS'] or counts['PARTIAL']:
        return 'PARTIAL'
    if counts['UNCERTAIN']:
        return 'UNCERTAIN'
    return 'FAILED'


async def process_notification_job(job: dict):
    if 'parts' not in job['result']:
        job['result'] = await prepare_notification(job)
        if not await checkpoint(job):
            return
    now = utc_now().timestamp()
    for part in job['result']['parts']:
        if not await _process_part(job, part, now):
            return
    parts = job['result']['parts']
    counts = {status: sum(part['status'] == status for part in parts) for status in ('SUCCESS', 'RETRY', 'FAILED', 'UNCERTAIN', 'PARTIAL')}
    job['result']['summary'] = {'parts': len(parts), **counts, 'attempts': sum(part['attempts'] for part in parts)}
    if counts['RETRY']:
        delay = max(1, int(min(part['retry_at'] for part in parts if part['status'] == 'RETRY') - utc_now().timestamp()))
        await checkpoint(job, 'RETRY', delay)
        return
    await checkpoint(job, _batch_status(parts, counts))
