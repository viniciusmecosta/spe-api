from datetime import date, timedelta

from pydantic import ValidationError

import pytest
from app.features.users.user_schemas import (
    UserBase,
    UserUpdate,
    UserUpdateMe,
    validate_cpf_logic,
)


def test_validate_cpf_logic():
    assert validate_cpf_logic("123") is False
    assert validate_cpf_logic("11111111111") is False
    assert validate_cpf_logic("12345678900") is False
    assert validate_cpf_logic("52998224725") is True


def test_user_base_valid():
    dob = date(2000, 1, 1)
    u_base = UserBase(username="TESTUSER", cpf="529.982.247-25", data_nascimento=dob)
    assert u_base.username == "testuser"
    assert u_base.cpf == "52998224725"

    u_base_none = UserBase(username=None, cpf=None)
    assert u_base_none.username is None
    assert u_base_none.cpf is None


def test_user_base_invalid_cpf():
    with pytest.raises(ValidationError):
        UserBase(cpf="12345678900")


def test_user_base_future_dob():
    future_date = date.today() + timedelta(days=1)
    with pytest.raises(ValidationError):
        UserBase(data_nascimento=future_date)


def test_user_update_valid():
    dob = date(1995, 5, 5)
    u_up = UserUpdate(username="ADMINUSER", cpf="529.982.247-25", data_nascimento=dob)
    assert u_up.username == "adminuser"
    assert u_up.cpf == "52998224725"

    u_up_none = UserUpdate(username=None, cpf=None)
    assert u_up_none.username is None
    assert u_up_none.cpf is None


def test_user_update_invalid_cpf():
    with pytest.raises(ValidationError):
        UserUpdate(cpf="invalid")


def test_user_update_future_dob():
    future_date = date.today() + timedelta(days=1)
    with pytest.raises(ValidationError):
        UserUpdate(data_nascimento=future_date)


def test_user_update_me_valid():
    dob = date(1990, 1, 1)
    u_me = UserUpdateMe(data_nascimento=dob)
    assert u_me.data_nascimento == dob


def test_user_update_me_future_dob():
    future_date = date.today() + timedelta(days=1)
    with pytest.raises(ValidationError):
        UserUpdateMe(data_nascimento=future_date)
