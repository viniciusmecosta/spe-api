from contextlib import contextmanager
from contextvars import ContextVar

request_id = ContextVar('request_id', default=None)


@contextmanager
def request_context(value):
    token = request_id.set(value)
    try:
        yield
    finally:
        request_id.reset(token)
