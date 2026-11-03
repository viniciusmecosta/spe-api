from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session


def lock_schedule_mutations(session: Session) -> None:
    bind = session.get_bind()
    if isinstance(bind, (Engine, Connection)) and bind.dialect.name == 'postgresql':
        session.execute(text('SELECT pg_advisory_xact_lock(5459015, 2)'))
