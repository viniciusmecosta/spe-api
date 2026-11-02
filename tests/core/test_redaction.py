import logging

from app.core.logger import CleanFormatter
from app.core.redaction import redact


def test_redacts_telegram_urls_database_passwords_and_named_secrets():
    result = redact('https://api.telegram.org/bot123:abc/sendDocument postgres://user:pass@host/db token=xyz senha="my password"')
    assert '123:abc' not in result
    assert 'user:pass' not in result
    assert 'xyz' not in result
    assert 'my password' not in result
    assert '/sendDocument' in result


def test_formatter_redacts_formatted_arguments_and_tracebacks():
    try:
        raise ValueError('password=hidden')
    except ValueError:
        import sys
        record = logging.LogRecord('test', logging.ERROR, '', 1, 'token=%s', ('sensitive',), sys.exc_info())
    rendered = CleanFormatter('%(levelname)s %(message)s').format(record)
    assert 'hidden' not in rendered
    assert 'sensitive' not in rendered
    assert 'ValueError' in rendered
