from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy import exists
from sqlalchemy.orm import Session

from app.features.users.user_exceptions import (
    BiometricValidationError,
    InsufficientPrivilegesError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from app.core.security import get_password_hash
from app.features.devices.device_models import UserBiometric
from app.features.system.audit_service import audit_service, serialize_model
from app.features.users.user_models import User
from app.features.users.user_repository import user_repository
from app.features.users.user_schemas import UserCreate, UserUpdate
from app.shared.enums import UserRole
from app.utils.formatters import format_name


class UserService:
    def _get_bio_attr(self, bio_data: Any, attr: str):
        if isinstance(bio_data, dict):
            return bio_data.get(attr)
        return getattr(bio_data, attr, None)

    def _validate_sensor_index(self, db: Session, user: User, sensor_idx: int, seen_indices: set):
        if sensor_idx is None:
            return
        if sensor_idx in seen_indices:
            raise BiometricValidationError(f"Índice biométrico {sensor_idx} enviado em duplicidade.")
        seen_indices.add(sensor_idx)

        query = db.query(UserBiometric).filter(UserBiometric.sensor_index == sensor_idx)
        if getattr(user, 'id', None):
            query = query.filter(UserBiometric.user_id != user.id)
        if db.query(query.exists()).scalar():
            raise BiometricValidationError(f"Índice biométrico {sensor_idx} já cadastrado em outro usuário.")

    def _validate_finger_id(self, finger_id: int, seen_fingers: set):
        if finger_id is None:
            return
        if finger_id in seen_fingers:
            raise BiometricValidationError(f"Biometria {finger_id} enviada em duplicidade.")
        seen_fingers.add(finger_id)

    def _process_single_biometric(self, db: Session, user: User, bio_data: Any, seen_indices: set, seen_fingers: set,
                                  current_biometrics: dict) -> UserBiometric:
        bio_id = self._get_bio_attr(bio_data, 'id')
        sensor_idx = self._get_bio_attr(bio_data, 'sensor_index')
        tmpl_data = self._get_bio_attr(bio_data, 'template_data')
        finger_id = self._get_bio_attr(bio_data, 'finger_id')

        self._validate_sensor_index(db, user, sensor_idx, seen_indices)
        self._validate_finger_id(finger_id, seen_fingers)

        if bio_id and bio_id in current_biometrics:
            existing = current_biometrics[bio_id]
            existing.sensor_index = sensor_idx
            if tmpl_data is not None:
                existing.template_data = tmpl_data
            existing.finger_id = finger_id
            return existing

        return UserBiometric(
            sensor_index=sensor_idx,
            template_data=tmpl_data,
            finger_id=finger_id
        )

    def _sync_biometrics(self, db: Session, user: User, biometrics_in: list):
        current_biometrics = {b.id: b for b in user.biometrics} if getattr(user, 'id', None) else {}
        new_biometrics_list = []
        seen_indices = set()
        seen_fingers = set()

        for bio_data in biometrics_in:
            processed_bio = self._process_single_biometric(db, user, bio_data, seen_indices, seen_fingers,
                                                           current_biometrics)
            new_biometrics_list.append(processed_bio)

        user.biometrics = new_biometrics_list

    def _validate_unique_fields(self, db: Session, user_in: Any, user: User | None = None):
        username = getattr(user_in, 'username', None)
        if username and (not user or username != user.username):
            if db.query(exists().where(User.username == username)).scalar():
                raise UserAlreadyExistsError("Nome de usuário já em uso.")

        email = getattr(user_in, 'email', None)
        if email and (not user or email != user.email):
            if db.query(exists().where(User.email == email)).scalar():
                raise UserAlreadyExistsError("E-mail já está em uso.")

        cpf = getattr(user_in, 'cpf', None)
        if cpf and (not user or cpf != user.cpf):
            if db.query(exists().where(User.cpf == cpf)).scalar():
                raise UserAlreadyExistsError("CPF já está em uso.")

    _format_name = staticmethod(format_name)

    def create_user(self, db: Session, user_in: UserCreate, current_user_id: int) -> User:
        self._validate_unique_fields(db, user_in)

        biometrics_in = getattr(user_in, 'biometrics', None)

        password_hash = get_password_hash(user_in.password)

        formatted_name = self._format_name(user_in.name or "")

        db_user = User(
            name=formatted_name,
            username=user_in.username,
            email=user_in.email,
            cpf=user_in.cpf,
            pis=user_in.pis,
            endereco=user_in.endereco,
            data_nascimento=user_in.data_nascimento,
            password_hash=password_hash,
            role=user_in.role,
            is_active=user_in.is_active,
            can_manual_punch_desktop=user_in.can_manual_punch_desktop,
            can_manual_punch_mobile=user_in.can_manual_punch_mobile,
            can_export_report=user_in.can_export_report
        )

        if biometrics_in:
            self._sync_biometrics(db, db_user, biometrics_in)

        db.add(db_user)
        db.commit()
        db.refresh(db_user)

        audit_service.log_change(db, current_user_id, "CREATE", new_model=db_user)
        return db_user

    def update_user(self, db: Session, user_id: int, user_in: UserUpdate, current_user_id: int) -> User:
        user = user_repository.get(db, user_id)
        if not user:
            raise UserNotFoundError(user_id=user_id)

        self._validate_unique_fields(db, user_in, user)

        update_data = user_in.model_dump(exclude_unset=True)
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
            db, current_user_id, "UPDATE",
            old_model=old_data, new_model=user,
            new_data={"password_changed": True} if password_changed else None
        )
        return user

    def disable_user(self, db: Session, user_id: int, current_user_id: int) -> User:
        user = user_repository.get(db, user_id)
        if not user:
            raise UserNotFoundError(user_id=user_id)

        user.is_active = False
        db.add(user)
        db.commit()
        db.refresh(user)

        audit_service.log_change(
            db, current_user_id, "DISABLE",
            entity="USER", entity_id=user.id,
            old_data={"is_active": True},
            new_data={"is_active": False}
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
        return user_repository.get_multi(
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
        user = user_repository.get(db, user_id=user_id)
        if not user:
            raise UserNotFoundError(user_id=user_id)

        if user.id != current_user.id and current_user.role not in [UserRole.MANAGER, UserRole.MAINTAINER]:
            raise InsufficientPrivilegesError("Privilégios insuficientes.", status_code=400)

        return user

    def update_user_by_admin(
            self, db: Session, user_id: int, user_in: UserUpdate, current_user: User
    ) -> User:
        user = user_repository.get(db, user_id=user_id)
        if not user:
            raise UserNotFoundError(user_id=user_id)

        if current_user.role == UserRole.MANAGER and user.role == UserRole.MAINTAINER:
            raise InsufficientPrivilegesError("Privilégios insuficientes para edição.")

        return self.update_user(db, user_id=user_id, user_in=user_in, current_user_id=current_user.id)


user_service = UserService()
