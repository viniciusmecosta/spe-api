from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.features.auth.auth_schemas import Token
from app.features.auth.auth_service import auth_service
from app.features.users.user_models import User
from app.features.users.user_schemas import UserResponse
from app.shared import deps
from app.shared.openapi_responses import BAD_REQUEST_RESPONSE, UNAUTHORIZED_RESPONSE

router = APIRouter()


@router.post(
    "/login",
    responses={**BAD_REQUEST_RESPONSE, **UNAUTHORIZED_RESPONSE},
)
def login_access_token(
        request: Request,
        db: Annotated[Session, Depends(deps.get_db)],
        form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> Token:
    request.state.attempted_user = form_data.username.lower()
    return auth_service.authenticate(
        db=db,
        username=form_data.username,
        password=form_data.password,
    )


@router.get(
    "/me",
    responses={**UNAUTHORIZED_RESPONSE},
)
def read_users_me(
        current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> UserResponse:
    return current_user
