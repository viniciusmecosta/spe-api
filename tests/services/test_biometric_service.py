from app.services.biometric_service import biometric_service


def test_get_available_sensor_indices(db_session_mock):
    db_session_mock.query.return_value.items = [(1,), (3,), (5,)]
    result = biometric_service.get_available_sensor_indices(db_session_mock)
    expected = set(range(1, 128)) - {1, 3, 5}
    assert result == sorted(list(expected))


def test_get_available_sensor_indices_empty(db_session_mock):
    db_session_mock.query.return_value.items = []
    result = biometric_service.get_available_sensor_indices(db_session_mock)
    expected = set(range(1, 128))
    assert result == sorted(list(expected))
