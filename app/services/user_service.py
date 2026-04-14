from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.domain.models.biometric import UserBiometric
from app.domain.models.user import User, WorkSchedule
from app.repositories.user_repository import user_repository
from app.schemas.user import UserCreate, UserUpdate
from app.services.audit_service import audit_service


class UserService:
    def create_user(self, db: Session, user_in: UserCreate, current_user_id: int) -> User:
        user = user_repository.get_by_username(db, username=user_in.username)
        if user:
            raise HTTPException(
                status_code=400,
                detail="The user with this username already exists.",
            )

        schedules_in = getattr(user_in, 'schedules', None)
        biometrics_in = getattr(user_in, 'biometrics', None)

        password_hash = get_password_hash(user_in.password)

        db_user = User(
            name=user_in.name,
            username=user_in.username,
            password_hash=password_hash,
            role=user_in.role,
            is_active=user_in.is_active,
            can_manual_punch_desktop=user_in.can_manual_punch_desktop,
            can_manual_punch_mobile=user_in.can_manual_punch_mobile,
            can_export_report=user_in.can_export_report
        )

        if schedules_in:
            for sch in schedules_in:
                if sch.daily_hours < 0 or sch.daily_hours > 24:
                    raise HTTPException(status_code=400, detail="Daily hours must be between 0 and 24")

                db_sch = WorkSchedule(
                    day_of_week=sch.day_of_week,
                    daily_hours=sch.daily_hours
                )
                db_user.schedules.append(db_sch)

        if biometrics_in:
            seen_indices = set()
            seen_fingers = set()
            for bio in biometrics_in:
                if bio.sensor_index is not None:
                    if bio.sensor_index in seen_indices:
                        raise HTTPException(status_code=400,
                                            detail=f"Index {bio.sensor_index} enviado duplicado na mesma requisicao.")
                    seen_indices.add(bio.sensor_index)

                    existing = db.query(UserBiometric).filter(
                        UserBiometric.sensor_index == bio.sensor_index
                    ).first()
                    if existing:
                        raise HTTPException(status_code=400,
                                            detail=f"Index {bio.sensor_index} ja cadastrado para outro usuario")

                if bio.finger_id is not None:
                    if bio.finger_id in seen_fingers:
                        raise HTTPException(status_code=400,
                                            detail=f"O dedo com ID {bio.finger_id} foi enviado mais de uma vez para o mesmo usuario.")
                    seen_fingers.add(bio.finger_id)

                db_bio = UserBiometric(
                    sensor_index=bio.sensor_index,
                    template_data=bio.template_data,
                    description=bio.description,
                    finger_id=bio.finger_id
                )
                db_user.biometrics.append(db_bio)

        db.add(db_user)
        db.commit()
        db.refresh(db_user)

        audit_service.log(
            db, actor_id=current_user_id, target_user_id=db_user.id, action="CREATE",
            entity="USER", entity_id=db_user.id,
            new_data={
                "username": db_user.username,
                "role": db_user.role,
                "name": db_user.name
            }
        )
        return db_user

    def update_user(self, db: Session, user_id: int, user_in: UserUpdate, current_user_id: int) -> User:
        user = user_repository.get(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if user_in.username and user_in.username != user.username:
            existing = user_repository.get_by_username(db, username=user_in.username)
            if existing:
                raise HTTPException(status_code=400, detail="Username already exists.")

        update_data = user_in.model_dump(exclude_unset=True)
        schedules_in = update_data.pop("schedules", None)
        biometrics_in = update_data.pop("biometrics", None)

        if "password" in update_data and update_data["password"]:
            update_data["password_hash"] = get_password_hash(update_data["password"])
            del update_data["password"]

        old_data = {
            "username": user.username,
            "role": user.role,
            "name": user.name,
            "is_active": user.is_active
        }

        for field, value in update_data.items():
            if hasattr(user, field):
                setattr(user, field, value)

        if schedules_in is not None:
            user.schedules.clear()
            for sch_data in schedules_in:
                daily_hours = sch_data['daily_hours'] if isinstance(sch_data, dict) else sch_data.daily_hours
                day_of_week = sch_data['day_of_week'] if isinstance(sch_data, dict) else sch_data.day_of_week

                if daily_hours < 0 or daily_hours > 24:
                    raise HTTPException(status_code=400, detail="Daily hours must be between 0 and 24")

                new_sch = WorkSchedule(day_of_week=day_of_week, daily_hours=daily_hours)
                user.schedules.append(new_sch)

        if biometrics_in is not None:
            current_biometrics = {b.id: b for b in user.biometrics}
            new_biometrics_list = []
            seen_indices = set()
            seen_fingers = set()

            for bio_data in biometrics_in:
                bio_id = bio_data.get('id') if isinstance(bio_data, dict) else bio_data.id
                sensor_idx = bio_data.get('sensor_index') if isinstance(bio_data, dict) else bio_data.sensor_index
                tmpl_data = bio_data.get('template_data') if isinstance(bio_data, dict) else bio_data.template_data
                desc = bio_data.get('description') if isinstance(bio_data, dict) else bio_data.description
                finger_id = bio_data.get('finger_id') if isinstance(bio_data, dict) else bio_data.finger_id

                if sensor_idx is not None:
                    if sensor_idx in seen_indices:
                        raise HTTPException(status_code=400,
                                            detail=f"Index {sensor_idx} enviado duplicado na mesma requisicao.")
                    seen_indices.add(sensor_idx)

                    existing = db.query(UserBiometric).filter(
                        UserBiometric.sensor_index == sensor_idx,
                        UserBiometric.user_id != user.id
                    ).first()
                    if existing:
                        raise HTTPException(status_code=400,
                                            detail=f"Index {sensor_idx} ja cadastrado para outro usuario")

                if finger_id is not None:
                    if finger_id in seen_fingers:
                        raise HTTPException(status_code=400,
                                            detail=f"O dedo com ID {finger_id} foi enviado mais de uma vez para o mesmo usuario.")
                    seen_fingers.add(finger_id)

                if bio_id and bio_id in current_biometrics:
                    existing = current_biometrics[bio_id]
                    existing.sensor_index = sensor_idx
                    if tmpl_data is not None:
                        existing.template_data = tmpl_data
                    existing.description = desc
                    existing.finger_id = finger_id
                    new_biometrics_list.append(existing)
                else:
                    new_bio = UserBiometric(
                        sensor_index=sensor_idx,
                        template_data=tmpl_data,
                        description=desc,
                        finger_id=finger_id
                    )
                    new_biometrics_list.append(new_bio)

            user.biometrics = new_biometrics_list

        db.add(user)
        db.commit()
        db.refresh(user)

        new_data = {
            "username": user.username,
            "role": user.role,
            "name": user.name,
            "is_active": user.is_active
        }

        audit_service.log(
            db, actor_id=current_user_id, target_user_id=user.id, action="UPDATE",
            entity="USER", entity_id=user.id,
            old_data=old_data, new_data=new_data
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
            db, actor_id=current_user_id, target_user_id=user.id, action="DISABLE",
            entity="USER", entity_id=user.id,
            old_data=old_data, new_data={"is_active": False}
        )
        return user

user_service = UserService()