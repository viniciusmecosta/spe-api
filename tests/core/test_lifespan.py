from fastapi import FastAPI

import pytest
from app.core.config import settings
from app.core.lifespan import lifespan


@pytest.mark.asyncio
async def test_lifespan_default():
    app = FastAPI()
    async with lifespan(app):
        pass


@pytest.mark.asyncio
async def test_lifespan_exportador(monkeypatch):
    monkeypatch.setattr(settings, "OPERATION_MODE", "EXPORTADOR")
    app = FastAPI()
    async with lifespan(app):
        pass
