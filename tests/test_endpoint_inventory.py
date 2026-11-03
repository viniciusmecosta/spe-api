from app.main import app


def test_no_deprecated_endpoints_are_exposed():
    paths = app.openapi()['paths']
    assert all(not operation.get('deprecated', False) for methods in paths.values()
               for operation in methods.values() if isinstance(operation, dict))


def test_canonical_endpoints_replace_legacy_routes():
    paths = app.openapi()['paths']
    for method, path in [
        ('post', '/time-records'), ('get', '/time-records'),
        ('post', '/time-records/{id}/type-transitions'), ('patch', '/time-records/{record_id}'),
        ('delete', '/time-records/{record_id}'), ('get', '/adjustments'),
        ('put', '/adjustments/{id}/review'), ('delete', '/adjustments/{id}'),
        ('get', '/reports/history'), ('get', '/anomalies'),
        ('post', '/payroll/{year}/{month}/transitions'), ('post', '/operations/jobs'),
    ]:
        assert method in paths['/api/v1' + path]
    for method, path in [
        ('post', '/time-records/entry'), ('post', '/time-records/exit'),
        ('get', '/time-records/my'), ('get', '/time-records/admin/list'),
        ('post', '/time-records/admin'), ('put', '/time-records/{id}/toggle'),
        ('put', '/time-records/admin/{record_id}'), ('delete', '/time-records/admin/{record_id}'),
        ('get', '/adjustments/my'), ('get', '/adjustments/'),
        ('put', '/adjustments/{id}/approve'), ('put', '/adjustments/{id}/reject'),
        ('delete', '/adjustments/admin/{id}'), ('get', '/reports/history/me'),
        ('get', '/reports/history/user/{user_id}'), ('get', '/anomalies/all'),
        ('get', '/anomalies/user/{user_id}'), ('post', '/payroll/close'),
        ('post', '/payroll/reopen'), ('post', '/backup/trigger'),
        ('post', '/telegram/manual-backup'), ('post', '/telegram/manual-report'),
    ]:
        assert method not in paths.get('/api/v1' + path, {})
