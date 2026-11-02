SENSITIVE_AUDIT_FIELDS = frozenset({
    "password", "password_hash", "api_key", "api_key_hash", "access_token",
    "refresh_token", "secret_key", "telegram_bot_token", "template_data",
})


def sanitize_audit_data(value):
    if isinstance(value, dict):
        return {
            key: sanitize_audit_data(item) for key, item in value.items()
            if str(key).casefold() not in SENSITIVE_AUDIT_FIELDS
        }
    if isinstance(value, list):
        return [sanitize_audit_data(item) for item in value]
    return value
