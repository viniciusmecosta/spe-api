from sqlalchemy import Column, Integer

from app.database.base import Base


class SampleModel(Base):
    id = Column(Integer, primary_key=True)


def test_base_tablename():
    assert SampleModel.__tablename__ == "samplemodel"


def test_models_indexes_and_alembic_env(monkeypatch):
    import importlib
    import importlib.util
    from pathlib import Path
    from unittest.mock import MagicMock, patch
    from sqlalchemy import Enum, String, Text
    from app.core.config import settings
    import app.database.models as db_models

    companies_table = db_models.Base.metadata.tables["companies"]
    existing_idx = next(idx for idx in companies_table.indexes if idx.name == "ix_companies_default_printer_id")
    companies_table.indexes.remove(existing_idx)
    importlib.reload(db_models)
    assert any(idx.name == "ix_companies_default_printer_id" for idx in companies_table.indexes)

    env_path = Path(__file__).resolve().parent.parent.parent / "alembic" / "env.py"
    mock_context = MagicMock()
    mock_config = MagicMock()
    mock_config.config_file_name = "alembic.ini"
    mock_config.config_ini_section = "alembic"
    mock_config.get_main_option.return_value = "postgresql://u:p@localhost/db"
    mock_config.get_section.return_value = {}
    mock_context.config = mock_config
    mock_context.is_offline_mode.return_value = True

    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn

    monkeypatch.setattr(settings, "SQLALCHEMY_DATABASE_URI", "postgresql+asyncpg://u:p%40@localhost/db")

    with (
        patch("alembic.context", mock_context),
        patch("logging.config.fileConfig") as mock_file_config,
        patch("sqlalchemy.engine_from_config", return_value=mock_engine),
    ):
        spec = importlib.util.spec_from_file_location("alembic_env_test", env_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        mock_file_config.assert_called_once_with("alembic.ini")
        assert module.compare_type(None, None, None, Text(), String()) is False
        assert module.compare_type(None, None, None, Text(), Enum("A", "B", native_enum=False)) is False
        assert module.compare_type(None, None, None, String(10), String(10)) is None
        module.run_migrations_online()

    mock_context.is_offline_mode.return_value = False
    mock_config.config_file_name = None
    monkeypatch.setattr(settings, "SQLALCHEMY_DATABASE_URI", "postgresql://u:p@localhost/db")
    with (
        patch("alembic.context", mock_context),
        patch("sqlalchemy.engine_from_config", return_value=mock_engine),
    ):
        spec2 = importlib.util.spec_from_file_location("alembic_env_test_online", env_path)
        module2 = importlib.util.module_from_spec(spec2)
        spec2.loader.exec_module(module2)


def test_alembic_version_migrations(mocker):
    import importlib.util
    from pathlib import Path
    import pytest

    versions_dir = Path(__file__).resolve().parent.parent.parent / "alembic" / "versions"
    mock_op = mocker.patch("alembic.op")

    for mig_file in sorted(versions_dir.glob("*.py")):
        spec = importlib.util.spec_from_file_location(f"mig_{mig_file.stem}", mig_file)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.upgrade()
        try:
            mod.downgrade()
        except NotImplementedError:
            pass
    assert mock_op.execute.called or mock_op.drop_column.called
