from collections.abc import Mapping
from typing import Any

from sqlalchemy.engine import make_url


def postgres_connection_params(uri: str, fallback: Mapping[str, Any]) -> dict[str, Any]:
    if uri:
        url = make_url(uri)
        if url.get_backend_name() != "postgresql":
            raise ValueError("A conexão deve usar PostgreSQL")
        return {
            "host": url.host or "localhost",
            "port": url.port or 5432,
            "user": url.username or "spe",
            "password": url.password or "",
            "dbname": url.database or "spe_db",
        }
    return {
        "host": fallback.get("POSTGRES_HOST") or "localhost",
        "port": int(fallback.get("POSTGRES_PORT") or 5432),
        "user": fallback.get("POSTGRES_USER") or "spe",
        "password": fallback.get("POSTGRES_PASSWORD") or "",
        "dbname": fallback.get("POSTGRES_DB") or "spe_db",
    }
