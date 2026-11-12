import json
from ipaddress import ip_network
from pathlib import Path
from re import fullmatch
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.engine import make_url

ROOT_DIR = Path(__file__).resolve().parent.parent.parent


def require_non_blank(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("o valor não pode ficar vazio")
    return value


def validate_app_version(value: str) -> str:
    if not fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", value):
        raise ValueError("APP_VERSION deve usar o formato X.Y.Z, por exemplo 2.0.2")
    return value


def validate_environment(value: str) -> str:
    if value.casefold() not in {"dev", "prod", "test"}:
        raise ValueError("ENVIRONMENT deve ser DEV, PROD ou TEST")
    return value.upper()


def validate_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("TIMEZONE deve ser um fuso horário IANA válido") from exc
    return value


def validate_database_uri(value: str) -> str:
    try:
        url = make_url(value)
    except Exception as exc:
        raise ValueError("SQLALCHEMY_DATABASE_URI deve ser uma URL PostgreSQL válida") from exc
    if url.drivername not in {"postgresql", "postgresql+asyncpg"} or not url.host or not url.database:
        raise ValueError("SQLALCHEMY_DATABASE_URI deve apontar para PostgreSQL com host e banco")
    return value


def validate_secret_key(value: str) -> str:
    if len(value.encode("utf-8")) < 32:
        raise ValueError("SECRET_KEY deve ter pelo menos 32 bytes")
    return value


def validate_algorithm(value: str) -> str:
    if value not in {"HS256", "HS384", "HS512"}:
        raise ValueError("ALGORITHM deve ser HS256, HS384 ou HS512")
    return value


def validate_proxy_networks(values: list[str]) -> list[str]:
    for value in values:
        ip_network(value, strict=False)
    return values


def assemble_cors_origins(values: list[str] | str) -> list[str]:
    if isinstance(values, str):
        if values.lstrip().startswith("["):
            values = json.loads(values)
        else:
            return [value.strip() for value in values.split(",")]
    if not isinstance(values, list):
        raise TypeError("BACKEND_CORS_ORIGINS deve ser uma lista de origens")
    return values


def validate_cors_origins(values: list[str]) -> list[str]:
    for origin in values:
        if origin == "*":
            continue
        parsed = urlsplit(origin)
        try:
            valid_port = parsed.port is None or 1 <= parsed.port <= 65535
        except ValueError:
            valid_port = False
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or not valid_port
        ):
            raise ValueError("BACKEND_CORS_ORIGINS deve conter origens HTTP ou HTTPS válidas")
    return values


def resolve_upload_dir(value: str) -> str:
    upload_path = Path(value)
    if not upload_path.is_absolute():
        upload_path = ROOT_DIR / upload_path
    return str(upload_path)
