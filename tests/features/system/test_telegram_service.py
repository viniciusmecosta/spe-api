from datetime import date, datetime
from unittest.mock import patch, MagicMock, mock_open

from sqlalchemy.exc import SQLAlchemyError

import pytest
import requests
from app.features.system.telegram_service import TelegramService
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import User
from app.shared.enums import RecordType


@pytest.fixture
def service():
    with patch("app.features.system.telegram_service.settings") as mock_settings:
        mock_settings.TELEGRAM_BOT_TOKEN = "test_token"
        mock_settings.TELEGRAM_CHAT_ID = "test_chat_id"
        mock_settings.TELEGRAM_MAX_MESSAGE_LENGTH = 4096
        yield TelegramService()


def test_init_no_token():
    with patch("app.features.system.telegram_service.settings") as mock_settings:
        mock_settings.TELEGRAM_BOT_TOKEN = ""
        mock_settings.TELEGRAM_CHAT_ID = ""
        service = TelegramService()
        assert service.bot_token == ""
        assert service.chat_id == ""


def test_send_text_success(service):
    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        result = service.send_text("test message")

        assert result is True
        mock_post.assert_called_once_with(
            "https://api.telegram.org/bottest_token/sendMessage",
            data={
                "chat_id": "test_chat_id",
                "text": "test message",
                "parse_mode": "HTML"
            },
            timeout=15
        )


def test_send_text_missing_credentials(service):
    service.bot_token = ""
    result = service.send_text("test")
    assert result is False


def test_send_text_failure_status(service):
    with patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_post.return_value = mock_response

        result = service.send_text("test")

        assert result is False


def test_send_text_request_exception(service):
    with patch("requests.post") as mock_post:
        mock_post.side_effect = requests.exceptions.RequestException("Error")
        result = service.send_text("test")
        assert result is False


def test_send_document_success(service):
    with patch("builtins.open", mock_open(read_data=b"data")), \
            patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        result = service.send_document("test.pdf", "caption")

        assert result is True
        mock_post.assert_called_once()


def test_send_document_missing_credentials(service):
    service.bot_token = ""
    result = service.send_document("test.pdf", "caption")
    assert result is False


def test_send_document_failure_status(service):
    with patch("builtins.open", mock_open(read_data=b"data")), \
            patch("requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Error"
        mock_post.return_value = mock_response

        result = service.send_document("test.pdf", "caption")

        assert result is False


def test_send_document_request_exception(service):
    with patch("builtins.open", mock_open(read_data=b"data")), \
            patch("requests.post") as mock_post:
        mock_post.side_effect = requests.exceptions.RequestException("Error")
        result = service.send_document("test.pdf", "caption")
        assert result is False


async def test_generate_report_text_no_records(service, async_db_mock):
    mock_result = MagicMock()
    mock_result.all.return_value = []
    async_db_mock.execute.return_value = mock_result

    start_date = date(2023, 1, 1)
    end_date = date(2023, 1, 1)

    result = await service.generate_report_text(async_db_mock, start_date, end_date)

    assert "Sem registros de ponto no período." in result


async def test_generate_report_text_with_records(service, async_db_mock):
    user = User(id=1, name="John Doe")
    record1 = TimeRecord(id=1, user_id=1, record_datetime=datetime(2023, 1, 1, 9, 0), record_type=RecordType.ENTRY)
    record2 = TimeRecord(id=2, user_id=1, record_datetime=datetime(2023, 1, 1, 18, 0), record_type=RecordType.EXIT)

    mock_result = MagicMock()
    mock_result.all.return_value = [(record1, user), (record2, user)]
    async_db_mock.execute.return_value = mock_result

    start_date = date(2023, 1, 1)
    end_date = date(2023, 1, 2)

    result = await service.generate_report_text(async_db_mock, start_date, end_date)

    assert "Relatório Gerencial" in result
    assert "01/01/2023" in result
    assert "John Doe" in result
    assert "E: 09:00" in result
    assert "S: 18:00" in result


async def test_generate_report_text_sqlalchemy_error(service, async_db_mock):
    async_db_mock.execute.side_effect = SQLAlchemyError("DB Error")

    start_date = date(2023, 1, 1)
    end_date = date(2023, 1, 1)

    result = await service.generate_report_text(async_db_mock, start_date, end_date)

    assert result == "Erro interno ao gerar relatório gerencial."


async def test_generate_report_text_exceed_max_length(service, async_db_mock):
    with patch("app.features.system.telegram_service.settings") as mock_settings:
        mock_settings.TELEGRAM_MAX_MESSAGE_LENGTH = 5

        user = User(id=1, name="John Doe")
        record1 = TimeRecord(id=1, user_id=1, record_datetime=datetime(2023, 1, 1, 9, 0), record_type=RecordType.ENTRY)

        mock_result = MagicMock()
        mock_result.all.return_value = [(record1, user)]
        async_db_mock.execute.return_value = mock_result

        start_date = date(2023, 1, 1)
        end_date = date(2023, 1, 1)

        result = await service.generate_report_text(async_db_mock, start_date, end_date)

        assert "John Doe" not in result


def test_group_daily_activity(service):
    user1 = User(id=1, name="John Doe")
    user2 = User(id=2, name="Jane Smith")
    record1 = TimeRecord(id=1, user_id=1, record_datetime=datetime(2023, 1, 1, 9, 0), record_type=RecordType.ENTRY)
    record2 = TimeRecord(id=2, user_id=1, record_datetime=datetime(2023, 1, 1, 18, 0), record_type=RecordType.EXIT)
    record3 = TimeRecord(id=3, user_id=2, record_datetime=datetime(2023, 1, 1, 10, 0), record_type=RecordType.ENTRY)

    records = [(record1, user1), (record2, user1), (record3, user2)]

    result = service._group_daily_activity(records)

    assert "01/01/2023" in result
    assert "John Doe" in result["01/01/2023"]
    assert "Jane Smith" in result["01/01/2023"]
    assert result["01/01/2023"]["John Doe"] == ["E: 09:00", "S: 18:00"]
    assert result["01/01/2023"]["Jane Smith"] == ["E: 10:00"]
