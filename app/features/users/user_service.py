from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.features.devices.device_models import UserBiometric
from app.features.system.audit_service import audit_service, serialize_model
from app.features.users.user_biometric_service import user_biometric_service
from app.features.users.user_exceptions import (
    BiometricValidationError,
    InsufficientPrivilegesError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from app.features.users.user_models import User
from app.features.users.user_repository import user_repository
from app.features.users.user_schemas import UserCreate, UserUpdate
from app.features.users.user_validator import user_validator
from app.shared.enums import UserRole
from app.utils.formatters import format_name


class UserService:
    def __init__(self):
        self.validator = user_validator
        self.biometric_service = user_biometric_service
        self.repository = user_repository

    def _get_bio_attr(self, bio_data: Any, attr: str) -> Any:
        return self.biometric_service._get_bio_attr(bio_data, attr)

    def _validate_sensor_index(
        self, db: Session, user: User, sensor_idx: int, seen_indices: set
    ) -> None:
        self.biometric_service.validate_sensor_index(db, user, sensor_idx, seen_indices)

    def _validate_finger_id(self, finger_id: int, seen_fingers: set) -> None:
        self.biometric_service.validate_finger_id(finger_id, seen_fingers)

    def _process_single_biometric(
        self,
        db: Session,
        user: User,
        bio_data: Any,
        seen_indices: set,
        seen_fingers: set,
        current_biometrics: dict,
    ) -> UserBiometric:
        return self.biometric_service.process_single_biometric(
            db, user, bio_data, seen_indices, seen_fingers, current_biometrics
        )

    def _sync_biometrics(self, db: Session, user: User, biometrics_in: list) -> None:
        self.biometric_service.sync_biometrics(db, user, biometrics_in)

    def _validate_unique_fields(
        self, db: Session, user_in: Any, user: User | None = None
    ) -> None:
        username = getattr(user_in, "username", None) if not isinstance(user_in, dict) else user_in.get("username")
        email = getattr(user_in, "email", None) if not isinstance(user_in, dict) else user_in.get("email")
        cpf = getattr(user_in, "cpf", None) if not isinstance(user_in, dict) else user_in.get("cpf")
        self.validator.validate_unique_fields(
            db, username=username, email=email, cpf=cpf, current_user=user
        )

    _format_name = staticmethod(format_name)

    def _extract_data(self, data_in: Any) -> dict[str, Any]:
        if isinstance(data_in, dict):
            return dict(data_in)
        if hasattr(data_in, "model_dump"):
            return data_in.model_dump(exclude_unset=True)
        return vars(data_in)

    def create_user(
        self, db: Session, user_in: UserCreate | dict[str, Any], current_user_id: int
    ) -> User:
        self._validate_unique_fields(db, user_in)
        data = self._extract_data(user_in)

        biometrics_in = data.pop("biometrics", None)
        password = data.pop("password", None)
        if password:
            data["password_hash"] = get_password_hash(password)

        if data.get("name"):
            data["name"] = self._format_name(data["name"])

        db_user = User(**data)

        if biometrics_in:
            self._sync_biometrics(db, db_user, biometrics_in)

        db.add(db_user)
        db.commit()
        db.refresh(db_user)

        audit_service.log_change(db, current_user_id, "CREATE", new_model=db_user)
        return db_user

    def update_user(
        self,
        db: Session,
        user_id: int,
        user_in: UserUpdate | dict[str, Any],
        current_user_id: int,
    ) -> User:
        user = self.repository.get(db, user_id)
        if not user:
            raise UserNotFoundError(user_id=user_id)

        self._validate_unique_fields(db, user_in, user)

        update_data = self._extract_data(user_in)
        biometrics_in = update_data.pop("biometrics", None)

        password_changed = False
        if update_data.get("password"):
            update_data["password_hash"] = get_password_hash(update_data["password"])
            del update_data["password"]
            password_changed = True

        if update_data.get("name"):
            update_data["name"] = self._format_name(update_data["name"])

        old_data = serialize_model(user)

        for field, value in update_data.items():
            if hasattr(user, field):
                setattr(user, field, value)

        if biometrics_in is not None:
            self._sync_biometrics(db, user, biometrics_in)

        db.add(user)
        db.commit()
        db.refresh(user)

        audit_service.log_change(
            db,
            current_user_id,
            "UPDATE",
            old_model=old_data,
            new_model=user,
            new_data={"password_changed": True} if password_changed else None,
        )
        return user

    def disable_user(self, db: Session, user_id: int, current_user_id: int) -> User:
        user = self.repository.get(db, user_id)
        if not user:
            raise UserNotFoundError(user_id=user_id)

        user.is_active = False
        db.add(user)
        db.commit()
        db.refresh(user)

        audit_service.log_change(
            db,
            current_user_id,
            "DISABLE",
            entity="USER",
            entity_id=user.id,
            old_data={"is_active": True},
            new_data={"is_active": False},
        )
        return user

    def get_multi(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        is_active: bool | None = None,
        role: str | None = None,
        search: str | None = None,
        order_by: str = "id",
        order_direction: str = "asc",
    ) -> list[User]:
        return self.repository.get_multi(
            db,
            skip=skip,
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

    def get_user_by_id(self, db: Session, user_id: int, current_user: User) -> User:
        user = self.repository.get(db, user_id=user_id)
        if not user:
            raise UserNotFoundError(user_id=user_id)

        self.validator.validate_read_privilege(current_user, user)
        return user

    def update_user_by_admin(
        self,
        db: Session,
        user_id: int,
        user_in: UserUpdate | dict[str, Any],
        current_user: User,
    ) -> User:
        user = self.repository.get(db, user_id=user_id)
        if not user:
            raise UserNotFoundError(user_id=user_id)

        self.validator.validate_manager_privilege(current_user, user)
        return self.update_user(
            db, user_id=user_id, user_in=user_in, current_user_id=current_user.id
        )


user_service = UserService()
