from app.main import app


def test_compatibility_routes_remain_deprecated():
    paths = app.openapi()['paths']
    for method, path in [
        ('post', '/time-records/entry'), ('post', '/time-records/exit'),
        ('get', '/time-records/my'), ('get', '/time-records/admin/list'),
        ('put', '/adjustments/{id}/approve'), ('put', '/adjustments/{id}/reject'),
        ('get', '/reports/history/me'), ('get', '/reports/history/user/{user_id}'),
    ]:
        assert paths['/api/v1' + path][method]['deprecated'] is True
