from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import settings
from app.features.companies.company_models import Company
from app.features.system.notification_context import (
    base_context,
    company_context,
    logo_file,
)


def test_logo_file_resolution(mocker, tmp_path):
    mocker.patch.object(settings, "UPLOAD_DIR", str(tmp_path))
    assert logo_file(None) is None
    assert logo_file("../secret.png") is None
    assert logo_file("missing.png") is None

    pub_dir = tmp_path / "public"
    pub_dir.mkdir()
    pub_logo = pub_dir / "logo.png"
    pub_logo.write_bytes(b"img")
    assert logo_file("logo.png") == pub_logo


@pytest.mark.asyncio
async def test_company_context_with_and_without_company():
    ctx_base = base_context()
    assert "project" in ctx_base

    session = MagicMock()
    session.scalar = AsyncMock(return_value=None)
    ctx_empty = await company_context(session)
    assert ctx_empty["project"] == settings.PROJECT_NAME

    comp = Company(id=1, name="ACME", cnpj="123", address="Rua 1", phone=None, logo_path=None)
    session.scalar = AsyncMock(return_value=comp)
    ctx_comp = await company_context(session)
    assert ctx_comp["company"] == "ACME"
    assert ctx_comp["phone"] == ""
    assert ctx_comp["logo_path"] == ""
