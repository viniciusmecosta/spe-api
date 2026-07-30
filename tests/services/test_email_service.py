import os
import smtplib
from io import BytesIO
from unittest.mock import MagicMock, mock_open, patch

import pytest

from app.domain.models.enums import UserRole
from app.domain.models.user import User
from app.services.email_service import EmailService, dispatch_payroll_email, email_service


@pytest.fixture(autouse=True)
def mock_settings():
    with patch("app.services.email_service.settings.SMTP_HOST", "smtp.test.com"), \
         patch("app.services.email_service.settings.SMTP_PORT", 587), \
         patch("app.services.email_service.settings.SMTP_USER", "user@test.com"), \
         patch("app.services.email_service.settings.SMTP_PASSWORD", "pass"), \
         patch("app.services.email_service.settings.ENVIRONMENT", "prod"), \
         patch("app.services.email_service.settings.TIMEZONE", "UTC"), \
         patch("app.services.email_service.settings.EMAIL_FROM", "test@test.com"):
        yield


@pytest.fixture
def mock_template_service():
    with patch("app.services.email_service.template_service") as mock:
        yield mock


@pytest.fixture
def mock_smtp():
    with patch("app.services.email_service.smtplib.SMTP") as mock:
        yield mock


@pytest.fixture
def local_mock_get_db_session(db_session_mock):
    with patch("app.database.session.get_db_session") as mock:
        mock.return_value.__enter__.return_value = db_session_mock
        yield mock


def test_send_payroll_email_no_smtp():
    with patch("app.services.email_service.settings.SMTP_HOST", None):
        service = EmailService()
        service.send_payroll_email("action", "user", 1, 2023, None, ["test@test.com"])


def test_send_payroll_email_no_maintainers():
    service = EmailService()
    service.send_payroll_email("action", "user", 1, 2023, None, [])


def test_send_payroll_email_success(mock_smtp, mock_template_service):
    mock_template_service.get_payroll_email_html.return_value = "<p>html</p>"
    service = EmailService()
    service.send_payroll_email("action", "user", 1, 2023, None, ["maintainer@test.com"])
    mock_smtp.assert_called_once_with("smtp.test.com", 587, timeout=60)
    server_instance = mock_smtp.return_value
    server_instance.sendmail.assert_called_once()
    server_instance.quit.assert_called_once()


def test_send_payroll_email_dev_env(mock_smtp, mock_template_service):
    with patch("app.services.email_service.settings.ENVIRONMENT", "dev"):
        mock_template_service.get_payroll_email_html.return_value = "<p>html</p>"
        service = EmailService()
        service.send_payroll_email("action", "user", 1, 2023, None, ["maintainer@test.com"])
        server_instance = mock_smtp.return_value
        sendmail_args = server_instance.sendmail.call_args
        assert "Folha de Ponto DEV - 01/2023" in sendmail_args[0][2]


def test_send_payroll_email_smtp_exception(mock_smtp, mock_template_service):
    mock_template_service.get_payroll_email_html.return_value = "<p>html</p>"
    mock_smtp.side_effect = smtplib.SMTPException("Error")
    service = EmailService()
    service.send_payroll_email("action", "user", 1, 2023, None, ["maintainer@test.com"])


def test_send_payroll_email_generic_exception(mock_smtp, mock_template_service):
    mock_template_service.get_payroll_email_html.return_value = "<p>html</p>"
    mock_smtp.side_effect = Exception("Error")
    service = EmailService()
    service.send_payroll_email("action", "user", 1, 2023, None, ["maintainer@test.com"])


def test_send_email_no_smtp():
    with patch("app.services.email_service.settings.SMTP_HOST", None):
        service = EmailService()
        assert service.send_email(["t@t.com"], [], "html", "period") is False


def test_send_email_no_to_emails():
    service = EmailService()
    assert service.send_email([], [], "html", "period") is False


def test_send_email_no_port():
    with patch("app.services.email_service.settings.SMTP_PORT", None):
        service = EmailService()
        assert service.send_email(["t@t.com"], [], "html", "period") is False


def test_send_email_success(mock_smtp, mock_template_service):
    mock_template_service.get_backup_email_html.return_value = "<html>"
    service = EmailService()
    assert service.send_email(["t@t.com"], [], "html", "period") is True
    server_instance = mock_smtp.return_value
    server_instance.sendmail.assert_called_once()
    server_instance.quit.assert_called_once()


def test_send_email_smtp_exception(mock_smtp, mock_template_service):
    mock_smtp.side_effect = smtplib.SMTPException("Err")
    service = EmailService()
    assert service.send_email(["t@t.com"], [], "html", "period") is False


def test_get_sender_address_prod():
    service = EmailService()
    assert service._get_sender_address() == "test@test.com"


def test_get_sender_address_no_from():
    with patch("app.services.email_service.settings.EMAIL_FROM", None):
        service = EmailService()
        assert service._get_sender_address() == "user@test.com"


def test_get_sender_address_no_from_no_user():
    with patch("app.services.email_service.settings.EMAIL_FROM", None), \
         patch("app.services.email_service.settings.SMTP_USER", None):
        service = EmailService()
        assert service._get_sender_address() == ""


def test_get_sender_address_dev_full():
    with patch("app.services.email_service.settings.ENVIRONMENT", "dev"), \
         patch("app.services.email_service.settings.EMAIL_FROM", "Test Name <test@test.com>"):
        service = EmailService()
        assert service._get_sender_address() == "DEVELOPMENT Test Name <test@test.com>"


def test_get_sender_address_dev_only_addr():
    with patch("app.services.email_service.settings.ENVIRONMENT", "dev"), \
         patch("app.services.email_service.settings.EMAIL_FROM", "test@test.com"):
        service = EmailService()
        assert service._get_sender_address() == "DEVELOPMENT <test@test.com>"


def test_get_sender_address_dev_no_addr():
    with patch("app.services.email_service.settings.ENVIRONMENT", "dev"), \
         patch("app.services.email_service.settings.EMAIL_FROM", "invalid"):
        service = EmailService()
        assert service._get_sender_address() == "DEVELOPMENT <invalid>"

def test_get_sender_address_dev_empty_email_from():
    with patch("app.services.email_service.settings.ENVIRONMENT", "dev"), \
         patch("app.services.email_service.settings.EMAIL_FROM", ""), \
         patch("app.services.email_service.settings.SMTP_USER", ""):
        service = EmailService()
        assert service._get_sender_address() == "DEVELOPMENT <>"


def test_build_payroll_message_with_attachment():
    service = EmailService()
    attachment = BytesIO(b"data")
    msg = service._build_payroll_message(["a@a.com"], "sub", "html", attachment, 1, 2023)
    assert msg["To"] == "a@a.com"
    assert msg["Subject"] == "sub"
    payloads = msg.get_payload()
    assert len(payloads) == 2


def test_build_backup_message_dev(mock_template_service):
    with patch("app.services.email_service.settings.ENVIRONMENT", "dev"):
        service = EmailService()
        msg = service._build_backup_message(["a@a.com"], [], "html", "period")
        assert "Backup SPE DEV" in msg["Subject"]


def test_build_backup_message_with_attachment(mock_template_service):
    with patch("os.path.exists", return_value=True), patch("builtins.open", mock_open(read_data=b"data")):
        service = EmailService()
        msg = service._build_backup_message(["a@a.com"], [("path", "file.txt")], "html", "period")
        payloads = msg.get_payload()
        assert len(payloads) == 2


def test_build_backup_message_attachment_not_exists(mock_template_service):
    with patch("os.path.exists", return_value=False):
        service = EmailService()
        msg = service._build_backup_message(["a@a.com"], [("path", "file.txt")], "html", "period")
        payloads = msg.get_payload()
        assert len(payloads) == 1
        assert payloads[0].get_content_type() == "text/html"


def test_dispatch_payroll_email_success():
    with patch.object(email_service, "send_payroll_email") as mock_send:
        dispatch_payroll_email("Fechamento", "User", 1, 2023, ["test@test.com"])
        mock_send.assert_called_once_with("Fechamento", "User", 1, 2023, None, ["test@test.com"])


def test_dispatch_payroll_email_exception():
    with patch.object(email_service, "send_payroll_email") as mock_send:
        mock_send.side_effect = Exception("Err")
        dispatch_payroll_email("Fechamento", "User", 1, 2023, ["test@test.com"])
        mock_send.assert_called_once()

