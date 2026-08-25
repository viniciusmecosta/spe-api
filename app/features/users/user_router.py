from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.features.users.user_models import User
from app.features.users.user_schemas import (
    UserCreate,
    UserResponse,
    UserUpdate,
    UserUpdateMe,
)
from app.features.users.user_service import UserService
from app.shared import deps
from app.shared.enums import UserRole
from app.shared.openapi_responses import (
    BAD_REQUEST_RESPONSE,
    CRUD_RESPONSES,
    FORBIDDEN_RESPONSE,
    NOT_FOUND_RESPONSE,
    UNAUTHORIZED_RESPONSE,
)

router = APIRouter(responses={**UNAUTHORIZED_RESPONSE})


@router.get(
    "/",
    responses={**FORBIDDEN_RESPONSE},
)
async def read_users(
        user_service: Annotated[UserService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
        after_id: Annotated[int | None, Query(ge=0)] = None,
        limit: Annotated[int, Query(ge=1, le=1000)] = 100,
        is_active: Annotated[bool | None, Query()] = None,
        role: Annotated[UserRole | None, Query()] = None,
        search: Annotated[str | None, Query()] = None,
        order_by: Annotated[
            str, Query(pattern="^(id|name|username|created_at|updated_at)$")
        ] = "id",
        order_direction: Annotated[str, Query(pattern="^(asc|desc)$")] = "asc",
) -> list[UserResponse]:
    role_value = role.value if role else None
    return await user_service.get_multi(
        after_id=after_id,
        limit=limit,
        is_active=is_active,
        role=role_value,
        search=search,
        order_by=order_by,
        order_direction=order_direction,
    )


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    responses={**BAD_REQUEST_RESPONSE, **FORBIDDEN_RESPONSE},
)
async def create_user(
        user_in: UserCreate,
        user_service: Annotated[UserService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> UserResponse:
    return await user_service.create_user(user_in=user_in, current_user_id=current_user.id)


@router.put(
    "/me",
    responses={**BAD_REQUEST_RESPONSE},
)
async def update_user_me(
        user_in: UserUpdateMe,
        user_service: Annotated[UserService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> UserResponse:
    update_data = UserUpdate(**user_in.model_dump(exclude_unset=True))
    return await user_service.update_user(
        user_id=current_user.id,
        user_in=update_data,
        current_user_id=current_user.id,
    )


@router.get("/me")
async def read_user_me(
        user_service: Annotated[UserService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> UserResponse:
    return user_service.get_user_me(current_user)


@router.get(
    "/{user_id}",
    responses={**BAD_REQUEST_RESPONSE, **NOT_FOUND_RESPONSE},
)
async def read_user_by_id(
        user_id: int,
        user_service: Annotated[UserService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_active_user)],
) -> UserResponse:
    return await user_service.get_user_by_id(user_id=user_id, current_user=current_user)


@router.put(
    "/{user_id}",
    responses={**BAD_REQUEST_RESPONSE, **CRUD_RESPONSES},
)
async def update_user(
        user_id: int,
        user_in: UserUpdate,
        user_service: Annotated[UserService, Depends()],
        current_user: Annotated[User, Depends(deps.get_current_manager)],
) -> UserResponse:
    return await user_service.update_user_by_admin(
        user_id=user_id, user_in=user_in, current_user=current_user
    )
