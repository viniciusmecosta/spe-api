from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api import deps
from app.domain.models.user import User
from app.schemas.token import Token
from app.schemas.user import UserResponse
from app.services.auth_service import auth_service

router = APIRouter()


@router.post(
    "/login",
    responses={
        400: {"description": "Usuário inativo"},
        401: {"description": "Credenciais incorretas"},
    },
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
    responses={
        401: {"description": "Não autenticado"},
    },
)
def read_users_me(
    current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> UserResponse:
    return current_user
