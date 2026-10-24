import smtplib
from unittest.mock import MagicMock

import pytest
import requests

from app.features.system.email_service import EmailService
from app.features.system.telegram_service import TelegramService


def telegram():
    service = TelegramService()
    service.bot_token, service.chat_id = 'synthetic-token', 'synthetic-chat'
    return service


def test_connect_timeout_retries_but_read_timeout_is_uncertain(mocker):
    service = telegram()
    post = mocker.patch('requests.post', side_effect=requests.exceptions.ConnectTimeout())
    sleep = mocker.patch('app.features.system.telegram_service.clock.sleep')
    assert not service.send_text('Mensagem')
    assert post.call_count == 4
    assert sleep.call_count == 3
    post.reset_mock()
    post.side_effect = requests.exceptions.ReadTimeout()
    assert not service.send_text('Mensagem')
    post.assert_called_once()


@pytest.mark.parametrize(('code', 'expected'), [(429, 'RETRY'), (503, 'RETRY'), (400, 'FAILED'), (401, 'FAILED')])
def test_telegram_statuses_and_retry_after(mocker, code, expected):
    response = MagicMock(status_code=code)
    response.json.return_value = {'parameters': {'retry_after': 17}}
    mocker.patch('requests.post', return_value=response)
    result = telegram().deliver_text('Mensagem')
    assert result.status == expected
    if code == 429:
        assert result.retry_after == 17


def test_long_telegram_text_preserves_all_content_and_escapes_html():
    from html import unescape
    text = '<b>Período</b>\n' + ('Pessoa &amp; Silva · E: 08:00 | S: 17:00\n' * 250)
    chunks = TelegramService.split_text(text)
    assert len(chunks) > 1
    assert all(len(chunk) <= 3500 for chunk in chunks)
    assert ''.join(unescape(chunk) for chunk in chunks) == 'Período\n' + ('Pessoa & Silva · E: 08:00 | S: 17:00\n' * 250)


def test_smtp_timeout_before_submission_retries_and_closes(mocker):
    from app.core.config import settings
    for key, value in {'SMTP_HOST': 'smtp.test', 'SMTP_PORT': 587, 'SMTP_USER': 'sender@test', 'SMTP_PASSWORD': 'synthetic'}.items():
        mocker.patch.object(settings, key, value)
    smtp = mocker.patch('smtplib.SMTP').return_value
    smtp.starttls.side_effect = TimeoutError()
    result = EmailService().deliver_email(['recipient@test'], [], '<p>Batidas</p>', 'Ontem')
    assert result.status == 'RETRY'
    smtp.quit.assert_called_once()
    smtp.sendmail.assert_not_called()


def test_smtp_timeout_after_submission_is_uncertain(mocker):
    from app.core.config import settings
    for key, value in {'SMTP_HOST': 'smtp.test', 'SMTP_PORT': 587, 'SMTP_USER': 'sender@test', 'SMTP_PASSWORD': 'synthetic'}.items():
        mocker.patch.object(settings, key, value)
    smtp = mocker.patch('smtplib.SMTP').return_value
    smtp.sendmail.side_effect = TimeoutError()
    smtp.quit.side_effect = smtplib.SMTPServerDisconnected()
    result = EmailService().deliver_email(['recipient@test'], [], '<p>Batidas</p>', 'Ontem')
    assert result.status == 'UNCERTAIN'
    smtp.close.assert_called_once()


def test_missing_attachment_prevents_successful_email(mocker):
    smtp = mocker.patch('smtplib.SMTP')
    result = EmailService().deliver_email(['recipient@test'], [('missing-file', 'backup.zip.enc')], 'Batidas', 'Ontem')
    assert result.status == 'FAILED'
    smtp.assert_not_called()


def test_email_context_is_dynamic_and_contains_no_journey_summary():
    from app.features.reports.template_service import TemplateService
    body = TemplateService.get_daily_report_html('Sexta-feira', '23/10/2026', True,
                                                 {'Ana <Silva>': [{'type': 'E', 'time': '07:00'}, {'type': 'S', 'time': '16:00'}]}, [])
    result = TemplateService.get_backup_email_html('Registros de ontem', body, {
        'company': 'Empresa Exemplo', 'version': '9.8.7', 'environment': 'homologação',
        'incidents': ['Falha temporária no envio'], 'logo_available': True,
    })
    for expected in ('Empresa Exemplo', '9.8.7', 'homologação', 'cid:company-logo', '07:00', '16:00',
                     'Ocorrências relevantes', '23/10/2026', '@media', 'Ana &lt;Silva&gt;'):
        assert expected in result
    for forbidden in ('Resumo de jornada', 'Último teste de restauração', 'Apuração diária', 'Não incluir tokens'):
        assert forbidden not in result
