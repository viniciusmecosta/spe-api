from unittest.mock import MagicMock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.database.schedule_lock import lock_schedule_mutations


def test_schedule_lock_skips_non_postgresql_database():
    engine = create_engine('sqlite://')
    try:
        with Session(engine) as session:
            assert lock_schedule_mutations(session) is None
            assert not session.in_transaction()
    finally:
        engine.dispose()


def test_schedule_lock_skips_unknown_bind():
    session = MagicMock()
    assert lock_schedule_mutations(session) is None
    session.execute.assert_not_called()
