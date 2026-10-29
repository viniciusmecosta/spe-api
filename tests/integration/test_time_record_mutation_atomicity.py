from unittest.mock import AsyncMock

import pytest
from test_mutation_atomicity import mutation_api, snapshot

from app.features.devices.device_service import DeviceService
from app.features.system.audit_service import audit_service
from app.shared.trusted_time_service import trusted_time_service

pytestmark = pytest.mark.asyncio
__all__ = ["mutation_api"]


async def test_manual_punch_rolls_back_when_ntp_audit_fails(mutation_api, pg_session_factory, monkeypatch):
    current_time, _ = trusted_time_service.get_trusted_time()
    monkeypatch.setattr(trusted_time_service, "get_trusted_time", lambda: (current_time, False))
    monkeypatch.setattr(audit_service, "async_log_change", AsyncMock(side_effect=RuntimeError("audit unavailable")))
    before = await snapshot(pg_session_factory, "record")

    await mutation_api.request("POST", "/time-records/entry", 500)

    assert await snapshot(pg_session_factory, "record") == before


async def test_biometric_punch_rolls_back_when_print_preparation_fails(mutation_api, pg_session_factory, monkeypatch):
    await mutation_api.request("POST", "/device-credentials/", 201, json={
        "name": "Dispositivo Sintetico", "key_type": "DEVICE", "api_key": "synthetic-device-key",
    })
    await mutation_api.request("PUT", "/users/1", json={
        "biometrics": [{"sensor_index": 12, "template_data": "SYNTHETIC_MANAGER", "finger_id": 0}],
    })
    before = await snapshot(pg_session_factory, "record")
    monkeypatch.setattr(DeviceService, "_handle_punch_side_effects", AsyncMock(side_effect=RuntimeError("print failure")))

    response = await mutation_api.json("POST", "/devices/punch", headers={"X-API-KEY": "synthetic-device-key"},
                                       json={"sensor_index": 12})

    assert response["line1"] == "Erro Interno"
    assert await snapshot(pg_session_factory, "record") == before
