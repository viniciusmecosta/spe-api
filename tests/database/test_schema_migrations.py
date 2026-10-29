from pathlib import Path
from unittest.mock import MagicMock


def test_migration_008_drops_and_restores_time_records_columns(monkeypatch):
    import importlib.util

    migration_path = Path(__file__).resolve().parents[2] / "alembic" / "versions" / "008_drop_time_records_platform.py"
    spec = importlib.util.spec_from_file_location("migration_008", migration_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.revision == "008"
    assert module.down_revision == "007"

    mock_op = MagicMock()
    monkeypatch.setattr(module, "op", mock_op)

    module.upgrade()
    assert mock_op.drop_column.call_count == 2
    mock_op.drop_column.assert_any_call("time_records", "platform")
    mock_op.drop_column.assert_any_call("time_records", "is_verified")

    module.downgrade()
    assert mock_op.add_column.call_count == 2
    first_table, first_col = mock_op.add_column.call_args_list[0].args
    second_table, second_col = mock_op.add_column.call_args_list[1].args
    assert first_table == "time_records"
    assert first_col.name == "is_verified"
    assert first_col.nullable is False
    assert second_table == "time_records"
    assert second_col.name == "platform"
    assert second_col.nullable is True
