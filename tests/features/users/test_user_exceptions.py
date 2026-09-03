from app.features.users.user_exceptions import (
    UserNotFoundError,
    UserAlreadyExistsError,
    InsufficientPrivilegesError,
    BiometricValidationError,
    SchedulePayrollClosedError,
    ScheduleOverlapError,
    BulkScheduleNotFoundError,
    BulkScheduleValidationError,
)


def test_all_user_exceptions():
    u1 = UserNotFoundError(10)
    assert "10" in u1.detail
    u1_none = UserNotFoundError()
    assert u1_none.detail == "Usuário não encontrado."

    u2 = UserAlreadyExistsError()
    assert "já em uso" in u2.detail

    u3 = InsufficientPrivilegesError()
    assert "insuficientes" in u3.detail

    u4 = BiometricValidationError("Invalid bio")
    assert u4.detail == "Invalid bio"

    u5 = SchedulePayrollClosedError("Closed")
    assert u5.detail == "Closed"

    u6 = ScheduleOverlapError()
    assert "Já existe" in u6.detail

    u7 = BulkScheduleNotFoundError("2026-01-01", "2026-01-31")
    assert "2026-01-01" in u7.detail
    u7_none = BulkScheduleNotFoundError()
    assert "não encontrado para esse período" in u7_none.detail

    u8 = BulkScheduleValidationError("Validation error")
    assert u8.detail == "Validation error"
