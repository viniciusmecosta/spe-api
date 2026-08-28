import pytest
from app.features.devices.biometric_service import biometric_service


@pytest.mark.asyncio
async def test_get_available_sensor_indices(async_db_mock):
    async_db_mock.scalar.side_effect = None
    async_db_mock.scalar.return_value = 5
    result = await biometric_service.get_available_sensor_indices(async_db_mock)
    assert result == list(range(6, 128))


@pytest.mark.asyncio
async def test_get_available_sensor_indices_empty(async_db_mock):
    async_db_mock.scalar.side_effect = None
    async_db_mock.scalar.return_value = None
    result = await biometric_service.get_available_sensor_indices(async_db_mock)
    assert result == list(range(1, 128))


@pytest.mark.asyncio
async def test_get_available_sensor_indices_full(async_db_mock):
    async_db_mock.scalar.side_effect = None
    async_db_mock.scalar.return_value = 127
    result = await biometric_service.get_available_sensor_indices(async_db_mock)
    assert result == []
