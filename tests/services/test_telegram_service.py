import pytest
from unittest.mock import patch, MagicMock, mock_open
from datetime import date, datetime, time
import requests
from sqlalchemy.exc import SQLAlchemyError

from app.services.telegram_service import TelegramService
from app.domain.models.enums import RecordType
from app.domain.models.time_record import TimeRecord
from app.domain.models.user import User

@pytest.fixture
def service():
    with patch("app.services.telegram_service.settings") as mock_settings:
        mock_settings.TELEGRAM_BOT_TOKEN = "test_token"
        mock_settings.TELEGRAM_CHAT_ID = "test_chat_id"
        mock_settings.TELEGRAM_MAX_MESSAGE_LENGTH = 4096
        yield TelegramService()

def test_init_no_token():
    with patch("app.services.telegram_service.settings") as mock_settings:
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

def test_generate_report_text_no_records(service, db_session_mock):
    mock_query = MagicMock()
    db_session_mock.query.return_value = mock_query
    mock_query.join.return_value = mock_query
    mock_query.filter.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    mock_query.all.return_value = []

    start_date = date(2023, 1, 1)
    end_date = date(2023, 1, 1)
    
    result = service.generate_report_text(db_session_mock, start_date, end_date)
    
    assert "Sem registros de ponto no período." in result

def test_generate_report_text_with_records(service, db_session_mock):
    mock_query = MagicMock()
    db_session_mock.query.return_value = mock_query
    mock_query.join.return_value = mock_query
    mock_query.filter.return_value = mock_query
    mock_query.order_by.return_value = mock_query
    
    user = User(id=1, name="John Doe")
    record1 = TimeRecord(id=1, user_id=1, record_datetime=datetime(2023, 1, 1, 9, 0), record_type=RecordType.ENTRY)
    record2 = TimeRecord(id=2, user_id=1, record_datetime=datetime(2023, 1, 1, 18, 0), record_type=RecordType.EXIT)
    
    mock_query.all.return_value = [(record1, user), (record2, user)]

    start_date = date(2023, 1, 1)
    end_date = date(2023, 1, 2)
    
    result = service.generate_report_text(db_session_mock, start_date, end_date)
    
    assert "Relatório Gerencial" in result
    assert "01/01/2023" in result
    assert "John Doe" in result
    assert "E: 09:00" in result
    assert "S: 18:00" in result

def test_generate_report_text_sqlalchemy_error(service, db_session_mock):
    db_session_mock.query.side_effect = SQLAlchemyError("DB Error")
    
    start_date = date(2023, 1, 1)
    end_date = date(2023, 1, 1)
    
    result = service.generate_report_text(db_session_mock, start_date, end_date)
    
    assert result == "Erro interno ao gerar relatório gerencial."

def test_generate_report_text_exceed_max_length(service, db_session_mock):
    with patch("app.services.telegram_service.settings") as mock_settings:
        mock_settings.TELEGRAM_MAX_MESSAGE_LENGTH = 5
        
        mock_query = MagicMock()
        db_session_mock.query.return_value = mock_query
        mock_query.join.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        
        user = User(id=1, name="John Doe")
        record1 = TimeRecord(id=1, user_id=1, record_datetime=datetime(2023, 1, 1, 9, 0), record_type=RecordType.ENTRY)
        
        mock_query.all.return_value = [(record1, user)]

        start_date = date(2023, 1, 1)
        end_date = date(2023, 1, 1)
        
        result = service.generate_report_text(db_session_mock, start_date, end_date)
        
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
