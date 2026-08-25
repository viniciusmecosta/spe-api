from app.features.devices.biometric_service import biometric_service


def test_get_available_sensor_indices(db_session_mock):
    db_session_mock.scalar.side_effect = None
    db_session_mock.scalar.return_value = 5
    result = biometric_service.get_available_sensor_indices(db_session_mock)
    assert result == list(range(6, 128))


def test_get_available_sensor_indices_empty(db_session_mock):
    db_session_mock.scalar.side_effect = None
    db_session_mock.scalar.return_value = None
    result = biometric_service.get_available_sensor_indices(db_session_mock)
    assert result == list(range(1, 128))


def test_get_available_sensor_indices_full(db_session_mock):
    db_session_mock.scalar.side_effect = None
    db_session_mock.scalar.return_value = 127
    result = biometric_service.get_available_sensor_indices(db_session_mock)
    assert result == []
