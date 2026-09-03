from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.users.user_models import User


def test_adjustment_request_user_name_property():
    adj1 = AdjustmentRequest(user=None)
    assert adj1.user_name == "Desconhecido"

    u = User(name="Carlos")
    adj2 = AdjustmentRequest(user=u)
    assert adj2.user_name == "Carlos"


def test_adjustment_invalid_status_error_branches():
    from app.features.adjustments.adjustment_exceptions import AdjustmentInvalidStatusError
    err1 = AdjustmentInvalidStatusError(current_status="APPROVED")
    assert "status 'APPROVED'" in err1.detail

    err2 = AdjustmentInvalidStatusError()
    assert "Apenas solicitações pendentes podem ser canceladas." in err2.detail

    err3 = AdjustmentInvalidStatusError(detail="Custom detail")
    assert err3.detail == "Custom detail"
