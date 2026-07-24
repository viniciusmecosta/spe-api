from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.domain.models.biometric import UserBiometric
from app.domain.models.user import User
from app.repositories.user_repository import user_repository
from app.schemas.user import UserCreate, UserUpdate
from app.services.audit_service import audit_service


class UserService:
    def _get_bio_attr(self, bio_data: any, attr: str):
        if isinstance(bio_data, dict):
            return bio_data.get(attr)
        return getattr(bio_data, attr, None)

    def _validate_sensor_index(self, db: Session, user: User, sensor_idx: int, seen_indices: set):
        if sensor_idx is None:
            return
        if sensor_idx in seen_indices:
            raise HTTPException(status_code=400, detail=f"Index {sensor_idx} enviado duplicado na mesma requisicao.")
        seen_indices.add(sensor_idx)

        query = db.query(UserBiometric).filter(UserBiometric.sensor_index == sensor_idx)
        if getattr(user, 'id', None):
            query = query.filter(UserBiometric.user_id != user.id)
        if query.first():
            raise HTTPException(status_code=400, detail=f"Index {sensor_idx} ja cadastrado para outro usuario")

    def _validate_finger_id(self, finger_id: int, seen_fingers: set):
        if finger_id is None:
            return
        if finger_id in seen_fingers:
            raise HTTPException(status_code=400, detail=f"O dedo com ID {finger_id} foi enviado mais de uma vez para o mesmo usuario.")
        seen_fingers.add(finger_id)

    def _process_single_biometric(self, db: Session, user: User, bio_data: any, seen_indices: set, seen_fingers: set, current_biometrics: dict) -> UserBiometric:
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
            processed_bio = self._process_single_biometric(db, user, bio_data, seen_indices, seen_fingers, current_biometrics)
            new_biometrics_list.append(processed_bio)

        user.biometrics = new_biometrics_list

    def _validate_unique_fields(self, db: Session, user_in: any, user: User = None):
        username = getattr(user_in, 'username', None)
        if username and (not user or username != user.username):
            if user_repository.get_by_username(db, username=username):
                raise HTTPException(status_code=400, detail="Um usuário com este nome de usuário já existe.")

        email = getattr(user_in, 'email', None)
        if email and (not user or email != user.email):
            if db.query(User).filter(User.email == email).first():
                raise HTTPException(status_code=400, detail="E-mail já está em uso.")

        cpf = getattr(user_in, 'cpf', None)
        if cpf and (not user or cpf != user.cpf):
            if db.query(User).filter(User.cpf == cpf).first():
                raise HTTPException(status_code=400, detail="CPF já está em uso.")

    def create_user(self, db: Session, user_in: UserCreate, current_user_id: int) -> User:
        self._validate_unique_fields(db, user_in)

        schedules_in = getattr(user_in, 'schedules', None)
        biometrics_in = getattr(user_in, 'biometrics', None)

        password_hash = get_password_hash(user_in.password)

        db_user = User(
            name=user_in.name,
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

        if schedules_in:
            from app.services.user_work_schedule_service import (
                user_work_schedule_service,
            )
            user_work_schedule_service.sync_user_schedules(db, db_user, schedules_in, is_create=True)

        if biometrics_in:
            self._sync_biometrics(db, db_user, biometrics_in)

        db.add(db_user)
        db.commit()
        db.refresh(db_user)

        audit_service.log(
            db, user_id=current_user_id, action="CREATE",
            entity="USER", entity_id=db_user.id,
            new_data={
                "username": db_user.username,
                "role": db_user.role,
                "name": db_user.name
            }
        )
        return db_user

    def _get_tracked_fields(self):
        return [
            "username", "role", "name", "is_active", "email", "cpf", 
            "pis", "endereco", "data_nascimento", "can_manual_punch_desktop", 
            "can_manual_punch_mobile", "can_export_report"
        ]

    def _capture_user_state(self, user: User) -> dict:
        state = {}
        for field in self._get_tracked_fields():
            if hasattr(user, field):
                val = getattr(user, field)
                state[field] = str(val) if val is not None else None
        return state

    def update_user(self, db: Session, user_id: int, user_in: UserUpdate, current_user_id: int) -> User:
        user = user_repository.get(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        self._validate_unique_fields(db, user_in, user)

        update_data = user_in.model_dump(exclude_unset=True)
        schedules_in = update_data.pop("schedules", None)
        biometrics_in = update_data.pop("biometrics", None)

        if update_data.get("password"):
            update_data["password_hash"] = get_password_hash(update_data["password"])
            del update_data["password"]
        
        old_data = self._capture_user_state(user)

        for field, value in update_data.items():
            if hasattr(user, field):
                setattr(user, field, value)

        if schedules_in is not None:
            from app.services.user_work_schedule_service import (
                user_work_schedule_service,
            )
            user_work_schedule_service.sync_user_schedules(db, user, schedules_in, is_create=False)

        if biometrics_in is not None:
            self._sync_biometrics(db, user, biometrics_in)

        db.add(user)
        db.commit()
        db.refresh(user)

        new_data_raw = self._capture_user_state(user)
                
        actual_old, actual_new = audit_service.compute_diffs(old_data, new_data_raw)

        audit_service.log(
            db, user_id=current_user_id, action="UPDATE",
            entity="USER", entity_id=user.id,
            old_data=actual_old, new_data=actual_new
        )
        return user

    def disable_user(self, db: Session, user_id: int, current_user_id: int) -> User:
        user = user_repository.get(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        old_data = {"is_active": user.is_active}

        user.is_active = False
        db.add(user)
        db.commit()
        db.refresh(user)

        audit_service.log(
            db, user_id=current_user_id, action="DISABLE",
            entity="USER", entity_id=user.id,
            old_data=old_data, new_data={"is_active": False}
        )
        return user

user_service = UserService()
