import pytest
from unittest.mock import MagicMock

from app.database.session import get_db, get_db_session


def test_get_db_session_exception():
    def _trigger():
        with get_db_session():
            raise RuntimeError("Database error test")

    with pytest.raises(RuntimeError, match="Database error test"):
        _trigger()


def test_get_db_session_success(mocker):
    mock_session = MagicMock()
    mocker.patch("app.database.session.SessionLocal", return_value=mock_session)
    with get_db_session() as s:
        assert s == mock_session
    mock_session.close.assert_called_once()


def test_get_db_generator(mocker):
    mock_session = MagicMock()
    mocker.patch("app.database.session.SessionLocal", return_value=mock_session)
    gen = get_db()
    s = next(gen)
    assert s == mock_session
    try:
        next(gen)
    except StopIteration:
        pass
    mock_session.close.assert_called_once()
