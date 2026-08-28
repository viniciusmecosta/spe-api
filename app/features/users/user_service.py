from typing import Annotated, Any

from fastapi import Depends
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_async_db
from app.features.system.audit_service import audit_service, serialize_model
from app.features.users.user_biometric_service import UserBiometricService
from app.features.users.user_exceptions import UserNotFoundError
from app.features.users.user_models import User
from app.features.users.user_repository import AsyncUserRepository, async_user_repository
from app.features.users.user_schemas import UserCreate, UserUpdate
from app.features.users.user_validator import UserValidator
from app.shared.enums import UserRole
from app.utils.formatters import format_name


class UserService:
    def __init__(
        self,
        db: Annotated[AsyncSession, Depends(get_async_db)],
        validator: Annotated[UserValidator, Depends()],
        biometric_service: Annotated[UserBiometricService, Depends()],
        repository: Annotated[AsyncUserRepository, Depends()] = None,
    ):
        self.db = db
        self.validator = validator
        self.biometric_service = biometric_service
        self._repository = repository

    @property
    def repository(self) -> AsyncUserRepository:
        return self._repository if self._repository is not None else async_user_repository

    @repository.setter
    def repository(self, value: AsyncUserRepository) -> None:
        self._repository = value

    async def _validate_unique_fields(
            self, user_in: Any, user: User | None = None
    ) -> None:
        username = getattr(user_in, "username", None) if not isinstance(user_in, dict) else user_in.get("username")
        email = getattr(user_in, "email", None) if not isinstance(user_in, dict) else user_in.get("email")
        cpf = getattr(user_in, "cpf", None) if not isinstance(user_in, dict) else user_in.get("cpf")
        await self.validator.validate_unique_fields(
            username=username, email=email, cpf=cpf, current_user=user
        )

    _format_name = staticmethod(format_name)

    def _extract_data(self, data_in: Any) -> dict[str, Any]:
        if isinstance(data_in, dict):
            return dict(data_in)
        if hasattr(data_in, "model_dump"):
            return data_in.model_dump(exclude_unset=True)
        return vars(data_in)

    async def create_user(
            self, user_in: UserCreate | dict[str, Any], current_user_id: int
    ) -> User:
        await self._validate_unique_fields(user_in)
        data = self._extract_data(user_in)

        if data.get("name"):
            data["name"] = self._format_name(data["name"])

        db_user = await self.repository.create(self.db, obj_in=data)

        await audit_service.async_log_change(self.db, current_user_id, "CREATE", new_model=db_user)
        return db_user

    async def update_user(
        self,
        user_id: int,
        user_in: UserUpdate | dict[str, Any],
        current_user_id: int,
    ) -> User:
        user = await self.repository.get(self.db, user_id)
        if not user:
            raise UserNotFoundError(user_id=user_id)

        await self._validate_unique_fields(user_in, user)

        update_data = self._extract_data(user_in)

        password_changed = False
        if update_data.get("password"):
            password_changed = True

        if update_data.get("name"):
            update_data["name"] = self._format_name(update_data["name"])

        old_data = serialize_model(user)

        user = await self.repository.update(self.db, db_obj=user, obj_in=update_data)

        await audit_service.async_log_change(
            self.db,
            current_user_id,
            "UPDATE",
            old_model=old_data,
            new_model=user,
            new_data={"password_changed": True} if password_changed else None,
        )
        return user

    async def get_multi(
        self,
            after_id: int | None = None,
        limit: int = 100,
        is_active: bool | None = None,
        role: str | None = None,
        search: str | None = None,
        order_by: str = "id",
        order_direction: str = "asc",
    ) -> list[User]:
        return await self.repository.get_multi(
            self.db,
            after_id=after_id,
            limit=limit,
            is_active=is_active,
            role=role,
            search=search,
            order_by=order_by,
            order_direction=order_direction,
        )

    def get_user_me(self, current_user: User) -> dict[str, Any]:
        can_punch_desktop = False
        can_punch_mobile = False

        if current_user.role in [UserRole.MANAGER, UserRole.MAINTAINER]:
            can_punch_desktop = True
            can_punch_mobile = True
        else:
            can_punch_desktop = current_user.can_manual_punch_desktop
            can_punch_mobile = current_user.can_manual_punch_mobile

        user_data = jsonable_encoder(current_user)
        user_data["can_manual_punch_desktop"] = can_punch_desktop
        user_data["can_manual_punch_mobile"] = can_punch_mobile
        return user_data

    async def get_user_by_id(self, user_id: int, current_user: User) -> User:
        user = await self.repository.get(self.db, user_id=user_id)
        if not user:
            raise UserNotFoundError(user_id=user_id)

        self.validator.validate_read_privilege(current_user, user)
        return user

    async def update_user_by_admin(
        self,
        user_id: int,
        user_in: UserUpdate | dict[str, Any],
        current_user: User,
    ) -> User:
        user = await self.repository.get(self.db, user_id=user_id)
        if not user:
            raise UserNotFoundError(user_id=user_id)

        self.validator.validate_manager_privilege(current_user, user)
        return await self.update_user(
            user_id=user_id, user_in=user_in, current_user_id=current_user.id
        )
