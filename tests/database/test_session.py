import pytest
from app.database.session import get_db_session, set_sqlite_pragma
from unittest.mock import MagicMock


def test_get_db_session_exception():
    def _trigger():
        with get_db_session():
            raise RuntimeError("Database error test")

    with pytest.raises(RuntimeError, match="Database error test"):
        _trigger()


def test_set_sqlite_pragma():
    mock_connection = MagicMock()
    mock_cursor = MagicMock()
    mock_connection.cursor.return_value = mock_cursor
    set_sqlite_pragma(mock_connection, None)
    assert mock_cursor.execute.call_count == 4
    mock_cursor.close.assert_called_once()
