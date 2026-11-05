from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import OAuth2PasswordRequestForm

from app.features.auth.auth_schemas import (
    PasswordChangeRequest,
    RefreshTokenRequest,
    Token,
)
from app.features.auth.auth_service import AuthService
from app.features.users.user_models import User
from app.features.users.user_schemas import UserResponse
from app.shared import deps
from app.shared.openapi_responses import BAD_REQUEST_RESPONSE, UNAUTHORIZED_RESPONSE


def prevent_token_caching(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


router = APIRouter(dependencies=[Depends(prevent_token_caching)])


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
    current_user: Annotated[User, Depends(deps.get_password_change_user)],
) -> UserResponse:
    return current_user


@router.post("/refresh", responses={**UNAUTHORIZED_RESPONSE})
async def refresh_access_token(
    payload: RefreshTokenRequest,
    auth_service: Annotated[AuthService, Depends()],
) -> Token:
    return await auth_service.refresh(payload.refresh_token)


@router.post("/logout", status_code=204)
async def logout(
    payload: RefreshTokenRequest,
    auth_service: Annotated[AuthService, Depends()],
) -> Response:
    await auth_service.logout(payload.refresh_token)
    return Response(status_code=204)


@router.post("/password", responses={**UNAUTHORIZED_RESPONSE})
async def change_password(
    payload: PasswordChangeRequest,
    current_user: Annotated[User, Depends(deps.get_password_change_user)],
    auth_service: Annotated[AuthService, Depends()],
) -> Token:
    return await auth_service.change_password(
        current_user, payload.current_password, payload.new_password
    )
