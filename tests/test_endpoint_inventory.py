import re
from pathlib import Path

from app.main import app


def test_endpoint_audit_covers_every_openapi_operation():
    audit = (Path(__file__).resolve().parents[1] / 'ENDPOINT_AUDIT.md').read_text()
    documented = set(re.findall(r'^\| (GET|POST|PUT|PATCH|DELETE) \| `([^`]+)` \|', audit, re.MULTILINE))
    operations = {
        (method.upper(), path.removeprefix('/api/v1'))
        for path, methods in app.openapi()['paths'].items()
        for method in methods
        if method.upper() in {'GET', 'POST', 'PUT', 'PATCH', 'DELETE'}
    }
    operations.update({('GET', '/'), ('GET', '/uploads/{filename}')})
    assert documented == operations


def test_compatibility_routes_remain_deprecated():
    paths = app.openapi()['paths']
    for method, path in [
        ('post', '/time-records/entry'), ('post', '/time-records/exit'),
        ('get', '/time-records/my'), ('get', '/time-records/admin/list'),
        ('put', '/adjustments/{id}/approve'), ('put', '/adjustments/{id}/reject'),
        ('get', '/reports/history/me'), ('get', '/reports/history/user/{user_id}'),
    ]:
        assert paths['/api/v1' + path][method]['deprecated'] is True
