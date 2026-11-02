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
    text = '<b>Período</b>\n' + ('Pessoa &amp; Nevoa · E: 08:00 | S: 17:00\n' * 250)
    chunks = TelegramService.split_text(text)
    assert len(chunks) > 1
    assert all(len(chunk) <= 3500 for chunk in chunks)
    assert ''.join(unescape(chunk) for chunk in chunks) == 'Período\n' + ('Pessoa & Nevoa · E: 08:00 | S: 17:00\n' * 250)


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
                                                 {'Ana <Nevoa>': [{'type': 'E', 'time': '07:00'}, {'type': 'S', 'time': '16:00'}]}, [])
    result = TemplateService.get_backup_email_html('Registros de ontem', body, {
        'company': 'Empresa Exemplo', 'version': '9.8.7', 'environment': 'homologação',
        'incidents': ['Falha temporária no envio'], 'logo_available': True,
    })
    for expected in ('Empresa Exemplo', '9.8.7', 'homologação', 'cid:company-logo', '07:00', '16:00',
                     'Ocorrências relevantes', '23/10/2026', '@media', 'Ana &lt;Nevoa&gt;'):
        assert expected in result
    for forbidden in ('Resumo de jornada', 'Último teste de restauração', 'Apuração diária', 'Não incluir tokens'):
        assert forbidden not in result


def test_backup_emails_distinguish_companies_and_are_not_replies():
    service = EmailService()
    first = service._build_backup_message(['recipient@example.test'], [], '', 'Ontem', {
        'company': 'Empresa Exemplo', 'cnpj': '11222333000181',
    })
    second = service._build_backup_message(['recipient@example.test'], [], '', 'Ontem', {
        'company': 'Empresa Alternativa', 'cnpj': '11222333000262',
    })
    assert 'Empresa Exemplo' in first['Subject']
    assert 'Empresa Alternativa' in second['Subject']
    assert 'CNPJ' not in first['Subject']
    assert '11.222.333/0001-81' not in first['Subject']
    assert first['Subject'] != second['Subject']
    assert first['Message-ID'] != second['Message-ID']
    for message in (first, second):
        assert message['In-Reply-To'] is None
        assert message['References'] is None


@pytest.mark.parametrize(('phone', 'formatted'), [
    ('85987654321', '(85) 98765-4321'),
    ('8533334444', '(85) 3333-4444'),
    ('(85) 98765-4321', '(85) 98765-4321'),
    ('+5585987654321', '+55 (85) 98765-4321'),
    ('(85) 3333-4444 ramal 1', '(85) 3333-4444 ramal 1'),
    ('123', '123'),
])
def test_email_company_contact_uses_formatted_cnpj_and_phone(phone, formatted):
    from app.features.reports.template_service import TemplateService
    body = TemplateService.get_backup_email_html('Ontem', '', {
        'company': 'Empresa Exemplo', 'cnpj': '11222333000181', 'phone': phone,
    })
    assert '11.222.333/0001-81' in body
    assert formatted in body
