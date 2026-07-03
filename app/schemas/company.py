import re
from typing import Optional

from pydantic import BaseModel, field_validator, ConfigDict


def validate_cnpj_logic(cnpj: str) -> bool:
    cnpj = re.sub(r'[^0-9]', '', cnpj)
    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False
    integers = [int(c) for c in cnpj]
    weights1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    sum1 = sum(a * b for a, b in zip(integers[:12], weights1))
    digit1 = 11 - (sum1 % 11)
    if digit1 >= 10:
        digit1 = 0
    if integers[12] != digit1:
        return False
    weights2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    sum2 = sum(a * b for a, b in zip(integers[:13], weights2))
    digit2 = 11 - (sum2 % 11)
    if digit2 >= 10:
        digit2 = 0
    if integers[13] != digit2:
        return False
    return True


class CompanyBase(BaseModel):
    name: str
    cnpj: str
    address: str
    phone: Optional[str] = None
    logo_path: Optional[str] = None

    @field_validator('cnpj')
    @classmethod
    def validate_cnpj(cls, v: str) -> str:
        v_clean = re.sub(r'[^0-9]', '', v)
        if not validate_cnpj_logic(v_clean):
            raise ValueError('CNPJ inválido')
        return v_clean


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(BaseModel):
    name: Optional[str] = None
    cnpj: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    logo_path: Optional[str] = None

    @field_validator('cnpj')
    @classmethod
    def validate_cnpj(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            v_clean = re.sub(r'[^0-9]', '', v)
            if not validate_cnpj_logic(v_clean):
                raise ValueError('CNPJ inválido')
            return v_clean
        return v


class CompanyResponse(CompanyBase):
    id: int

    model_config = ConfigDict(from_attributes=True)
