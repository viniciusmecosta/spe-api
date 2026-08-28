from datetime import date, datetime
from unittest.mock import AsyncMock, patch

import pytest
from app.features.reports.daily_report_service import DailyReportService
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import User
from app.shared.enums import RecordType


@pytest.fixture
def service():
    return DailyReportService()


@patch("app.features.reports.daily_report_service.anomaly_service")
@patch("app.features.reports.daily_report_service.template_service")
def test_generate_daily_report_html_with_records(mock_template_service, mock_anomaly_service, service, db_session_mock):
    target_date = date(2026, 7, 24)

    user = User(id=1, name="John Doe")
    record1 = TimeRecord(
        id=1,
        user_id=1,
        record_type=RecordType.ENTRY,
        record_datetime=datetime(2026, 7, 24, 8, 0, 0),
        is_ignored=False
    )
    record2 = TimeRecord(
        id=2,
        user_id=1,
        record_type=RecordType.EXIT,
        record_datetime=datetime(2026, 7, 24, 18, 0, 0),
        is_ignored=False
    )

    class QueryMock:
        def __init__(self, items):
            self.items = items

        def join(self, *args, **kwargs):
            return self

        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def all(self):
            return self.items

    db_session_mock.query.return_value = QueryMock([(record1, user), (record2, user)])

    class AnomalyMock:
        def __init__(self, user_name, description):
            self.user_name = user_name
            self.description = description

    mock_anomaly_service.get_anomalies = AsyncMock(return_value=[AnomalyMock("Jane Smith", "Missing Exit")])
    mock_template_service.get_daily_report_html.return_value = "<html>Mock HTML</html>"

    result = service.generate_daily_report_html(db_session_mock, target_date)

    assert result == "<html>Mock HTML</html>"
    mock_template_service.get_daily_report_html.assert_called_once()
    args = mock_template_service.get_daily_report_html.call_args[0]
    assert args[0] == "Sexta-feira"
    assert args[1] == "24/07/2026"
    assert args[2] is True
    assert "John Doe" in args[3]
    assert args[3]["John Doe"][0] == {"time": "08:00", "type": "E"}
    assert args[3]["John Doe"][1] == {"time": "18:00", "type": "S"}
    assert args[4] == ["<strong>Jane Smith</strong>: Missing Exit"]


@patch("app.features.reports.daily_report_service.anomaly_service")
@patch("app.features.reports.daily_report_service.template_service")
def test_generate_daily_report_html_no_records(mock_template_service, mock_anomaly_service, service, db_session_mock):
    target_date = date(2026, 7, 24)

    class QueryMock:
        def __init__(self, items):
            self.items = items

        def join(self, *args, **kwargs):
            return self

        def filter(self, *args, **kwargs):
            return self

        def order_by(self, *args, **kwargs):
            return self

        def all(self):
            return self.items

    db_session_mock.query.return_value = QueryMock([])

    mock_anomaly_service.get_anomalies = AsyncMock(return_value=[])
    mock_template_service.get_daily_report_html.return_value = "<html>Mock HTML No Records</html>"

    result = service.generate_daily_report_html(db_session_mock, target_date)

    assert result == "<html>Mock HTML No Records</html>"
    mock_template_service.get_daily_report_html.assert_called_once()
    args = mock_template_service.get_daily_report_html.call_args[0]
    assert args[0] == "Sexta-feira"
    assert args[1] == "24/07/2026"
    assert args[2] is False
    assert args[3] == {}
    assert args[4] == []


def test_generate_daily_report_html_exception(service, db_session_mock):
    target_date = date(2026, 7, 24)

    db_session_mock.query.side_effect = ValueError("Database Error")

    result = service.generate_daily_report_html(db_session_mock, target_date)

    assert result == "<p><em>Erro ao gerar relatório para 2026-07-24.</em></p>"
