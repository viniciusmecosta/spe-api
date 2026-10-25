import re
from urllib.parse import quote

from app.core.config import settings

_TOKEN = re.compile(r"(api\.telegram\.org/bot)[^/\s]+", re.IGNORECASE)
_CREDENTIAL = re.compile(
    r"(?i)((?:password|senha|secret|token|authorization|api[_-]?key)\s*[=:]\s*)"
    r"(?:Bearer\s+)?(?:\"[^\"]*\"|'[^']*'|[^\s,;}&]+)"
)
_DATABASE = re.compile(r"(\b[a-zA-Z][a-zA-Z0-9+.-]{0,30}://[^:/\s]{1,256}:)[^@\s]{1,2048}(@)")


def redact(value: str) -> str:
    result = _TOKEN.sub(r"\1[REDACTED]", value)
    result = _DATABASE.sub(r"\1[REDACTED]\2", result)
    result = _CREDENTIAL.sub(r"\1[REDACTED]", result)
    for name in ("TELEGRAM_BOT_TOKEN", "SMTP_PASSWORD", "SECRET_KEY", "POSTGRES_PASSWORD",
                 "FIRST_SUPERUSER_PASSWORD"):
        secret = getattr(settings, name, None)
        if isinstance(secret, str) and len(secret) >= 4:
            result = result.replace(secret, "[REDACTED]").replace(quote(secret, safe=""), "[REDACTED]")
    return result
