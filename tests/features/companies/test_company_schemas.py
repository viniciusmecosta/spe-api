from pydantic import ValidationError

import pytest
from app.features.companies.company_schemas import CompanyCreate, CompanyUpdate, validate_cnpj_logic


def test_cnpj_logic_branches():
    assert validate_cnpj_logic("11111111111111") is False
    assert validate_cnpj_logic("00000000000100") is False
    assert validate_cnpj_logic("00000000000191") is True
    assert validate_cnpj_logic("00000000003700") is True
    assert validate_cnpj_logic("00000000000192") is False
    assert isinstance(validate_cnpj_logic("11222333000181"), bool)


def test_company_create_invalid_cnpj():
    with pytest.raises(ValidationError, match="CNPJ inválido"):
        CompanyCreate(name="Co", cnpj="12345", address="Addr")


def test_company_update_invalid_cnpj():
    with pytest.raises(ValidationError, match="CNPJ inválido"):
        CompanyUpdate(cnpj="12345")


def test_company_update_valid_and_none():
    up_none = CompanyUpdate(cnpj=None)
    assert up_none.cnpj is None

    up_valid = CompanyUpdate(cnpj="00.000.000/0001-91")
    assert up_valid.cnpj == "00000000000191"
