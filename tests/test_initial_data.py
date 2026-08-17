import runpy
from unittest.mock import MagicMock, patch
import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.initial_data import init_db, main


def test_init_db_creates_user(db_session):
    with patch("app.initial_data.user_repository.get_by_username", return_value=None):
        with patch("app.initial_data.get_password_hash", return_value="hashed"):
            init_db(db_session)


def test_init_db_user_exists(db_session):
    fake_user = MagicMock()
    with patch("app.initial_data.user_repository.get_by_username", return_value=fake_user):
        init_db(db_session)


def test_main_success():
    mock_db = MagicMock()
    with patch("app.initial_data.get_db_session") as mock_get_db:
        mock_get_db.return_value.__enter__.return_value = mock_db
        with patch("app.initial_data.init_db") as mock_init:
            main()
            mock_init.assert_called_once_with(mock_db)


def test_main_sqlalchemy_error():
    with patch("app.initial_data.get_db_session") as mock_get_db:
        mock_get_db.return_value.__enter__.side_effect = SQLAlchemyError("DB error")
        with pytest.raises(SQLAlchemyError):
            main()


def test_initial_data_module_main():
    mock_db = MagicMock()
    with patch("app.initial_data.get_db_session") as mock_get_db:
        mock_get_db.return_value.__enter__.return_value = mock_db
        with patch("app.initial_data.init_db"):
            runpy.run_module("app.initial_data", run_name="__main__")
