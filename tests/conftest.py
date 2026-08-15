from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo
import pytest
from sqlalchemy.orm import Session

import app.features.adjustments.adjustment_models
import app.features.companies.company_models
import app.features.devices.device_models
import app.features.holidays.holiday_models
import app.features.payroll.payroll_models
import app.features.printers.printer_models
import app.features.system.system_models
import app.features.time_records.time_record_models
import app.features.users.user_models
from app.core.config import settings

@pytest.fixture
def db_session_mock():
    session = MagicMock(spec=Session)
    
    class QueryMock:
        def __init__(self, items=None):
            self.items = items or []
            
        def filter(self, *args, **kwargs):
            return self
            
        def order_by(self, *args, **kwargs):
            return self
            
        def first(self):
            return self.items[0] if self.items else None
            
        def all(self):
            return self.items
            
        def delete(self, *args, **kwargs):
            return len(self.items)

    session.query.return_value = QueryMock()
    return session

@pytest.fixture
def mock_get_db_session(mocker, db_session_mock):
    mock = mocker.patch("app.database.session.get_db_session")
    
    class ContextManagerMock:
        def __enter__(self):
            return db_session_mock
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
            
    mock.return_value = ContextManagerMock()
    return mock

@pytest.fixture
def current_time():
    return datetime.now(ZoneInfo(settings.TIMEZONE))
