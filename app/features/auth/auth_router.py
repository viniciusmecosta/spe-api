from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm

from app.features.auth.auth_schemas import Token
from app.features.auth.auth_service import AuthService
from app.features.users.user_models import User
from app.features.users.user_schemas import UserResponse
from app.shared import deps
from app.shared.openapi_responses import BAD_REQUEST_RESPONSE, UNAUTHORIZED_RESPONSE

router = APIRouter()


@router.post(
    "/login",
    responses={**BAD_REQUEST_RESPONSE, **UNAUTHORIZED_RESPONSE},
)
async def login_access_token(
        request: Request,
        auth_service: Annotated[AuthService, Depends()],
        form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Token:
    return await auth_service.authenticate(
        form_data=form_data,
        request=request,
    )


@router.get(
    "/me",
    responses={**UNAUTHORIZED_RESPONSE},
)
async def read_users_me(
        current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> UserResponse:
    return current_user
