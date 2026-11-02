from collections.abc import Iterable

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

PAYROLL_LOCK_NAMESPACE = 0x535045


def lock_payroll_periods(
    session: Session,
    periods: Iterable[tuple[int, int]],
    *,
    exclusive: bool = False,
) -> bool:
    bind = session.get_bind()
    if not isinstance(bind, (Engine, Connection)) or bind.dialect.name != "postgresql":
        return False
    function = "pg_advisory_xact_lock" if exclusive else "pg_advisory_xact_lock_shared"
    for year, month in sorted(set(periods)):
        session.execute(
            text(f"SELECT {function}(:namespace, :period)"),
            {"namespace": PAYROLL_LOCK_NAMESPACE, "period": year * 100 + month},
        )
    return True
