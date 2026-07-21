from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.security import get_password_hash
from app.domain.models.biometric import UserBiometric
from app.domain.models.user import User, UserWorkScheduleConfig
from app.repositories.user_repository import user_repository
from app.repositories.payroll_repository import payroll_repository
from app.schemas.user import UserCreate, UserUpdate
from app.services.audit_service import audit_service
from datetime import date

class UserService:
    def _check_payroll_closure(self, db: Session, valid_from: date, valid_until: date = None):
        start_year = valid_from.year
        start_month = valid_from.month

        end_date = valid_until if valid_until else date.today()
        end_year = end_date.year
        end_month = end_date.month
        
        current_year = start_year
        current_month = start_month
        
        while (current_year < end_year) or (current_year == end_year and current_month <= end_month):
            closure = payroll_repository.get_by_month(db, current_month, current_year)
            if closure and closure.is_closed:
                raise HTTPException(
                    status_code=403, 
                    detail=f"Não é permitido alterar configurações de expediente. A folha de ponto de {current_month:02d}/{current_year} já está fechada."
                )
            current_month += 1
            if current_month > 12:
                current_month = 1
                current_year += 1

    def create_user(self, db: Session, user_in: UserCreate, current_user_id: int) -> User:
        user = user_repository.get_by_username(db, username=user_in.username)
        if user:
            raise HTTPException(
                status_code=400,
                detail="Um usuário com este nome de usuário já existe.",
            )

        if getattr(user_in, 'email', None):
            if db.query(User).filter(User.email == user_in.email).first():
                raise HTTPException(status_code=400, detail="E-mail já está em uso.")

        if getattr(user_in, 'cpf', None):
            if db.query(User).filter(User.cpf == user_in.cpf).first():
                raise HTTPException(status_code=400, detail="CPF já está em uso.")

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
            from datetime import date
            today = date.today()
            for sch in schedules_in:
                if sch.daily_hours < 0 or sch.daily_hours > 24:
                    raise HTTPException(status_code=400, detail="As horas diárias devem estar entre 0 e 24.")

                db_sch = UserWorkScheduleConfig(
                    day_of_week=sch.day_of_week,
                    daily_hours=sch.daily_hours,
                    entry_1=sch.entry_1,
                    exit_1=sch.exit_1,
                    entry_2=sch.entry_2,
                    exit_2=sch.exit_2,
                    valid_from=sch.valid_from if sch.valid_from else today,
                    valid_until=sch.valid_until
                )
                db_user.historical_schedules.append(db_sch)

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
                    finger_id=bio.finger_id
                )
                db_user.biometrics.append(db_bio)

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

    def update_user(self, db: Session, user_id: int, user_in: UserUpdate, current_user_id: int) -> User:
        user = user_repository.get(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if user_in.username and user_in.username != user.username:
            existing = user_repository.get_by_username(db, username=user_in.username)
            if existing:
                raise HTTPException(status_code=400, detail="Username already exists.")

        if user_in.email and user_in.email != user.email:
            existing_email = db.query(User).filter(User.email == user_in.email).first()
            if existing_email:
                raise HTTPException(status_code=400, detail="E-mail já está em uso.")

        if user_in.cpf and user_in.cpf != user.cpf:
            existing_cpf = db.query(User).filter(User.cpf == user_in.cpf).first()
            if existing_cpf:
                raise HTTPException(status_code=400, detail="CPF já está em uso.")

        update_data = user_in.model_dump(exclude_unset=True)
        schedules_in = update_data.pop("schedules", None)
        biometrics_in = update_data.pop("biometrics", None)

        if "password" in update_data and update_data["password"]:
            update_data["password_hash"] = get_password_hash(update_data["password"])
            del update_data["password"]

        tracked_fields = [
            "username", "role", "name", "is_active", "email", "cpf", 
            "pis", "endereco", "data_nascimento", "can_manual_punch_desktop", 
            "can_manual_punch_mobile", "can_export_report"
        ]
        
        old_data = {}
        for field in tracked_fields:
            if hasattr(user, field):
                val = getattr(user, field)
                old_data[field] = str(val) if val is not None else None

        for field, value in update_data.items():
            if hasattr(user, field):
                setattr(user, field, value)

        if schedules_in is not None:
            from datetime import date
            today = date.today()
            
            current_sch_ids = [s.id for s in user.current_schedules]
            incoming_ids = [s.id for s in schedules_in if getattr(s, 'id', None) is not None]
            
            schedules_to_remove = [sch for sch in user.historical_schedules if sch.id in current_sch_ids and sch.id not in incoming_ids]
            for sch in schedules_to_remove:
                self._check_payroll_closure(db, sch.valid_from, sch.valid_until)
                user.historical_schedules.remove(sch)

            for sch_data in schedules_in:
                sch_id = getattr(sch_data, 'id', None)
                daily_hours = getattr(sch_data, 'daily_hours')
                day_of_week = getattr(sch_data, 'day_of_week')
                entry_1 = getattr(sch_data, 'entry_1', None)
                exit_1 = getattr(sch_data, 'exit_1', None)
                entry_2 = getattr(sch_data, 'entry_2', None)
                exit_2 = getattr(sch_data, 'exit_2', None)
                valid_from = getattr(sch_data, 'valid_from', None)
                valid_until = getattr(sch_data, 'valid_until', None)

                if daily_hours < 0 or daily_hours > 24:
                    raise HTTPException(status_code=400, detail="Daily hours must be between 0 and 24")

                if sch_id:
                    existing_sch = next((sch for sch in user.historical_schedules if sch.id == sch_id), None)
                    if existing_sch:
                        self._check_payroll_closure(db, existing_sch.valid_from, existing_sch.valid_until)
                        new_valid_from = valid_from if valid_from else today
                        self._check_payroll_closure(db, new_valid_from, valid_until)
                        
                        existing_sch.day_of_week = day_of_week
                        existing_sch.daily_hours = daily_hours
                        existing_sch.entry_1 = entry_1
                        existing_sch.exit_1 = exit_1
                        existing_sch.entry_2 = entry_2
                        existing_sch.exit_2 = exit_2
                        existing_sch.valid_from = new_valid_from
                        existing_sch.valid_until = valid_until
                else:
                    new_valid_from = valid_from if valid_from else today
                    self._check_payroll_closure(db, new_valid_from, valid_until)
                    
                    new_sch = UserWorkScheduleConfig(
                        day_of_week=day_of_week, 
                        daily_hours=daily_hours,
                        entry_1=entry_1,
                        exit_1=exit_1,
                        entry_2=entry_2,
                        exit_2=exit_2,
                        valid_from=new_valid_from,
                        valid_until=valid_until
                    )
                    user.historical_schedules.append(new_sch)

        if biometrics_in is not None:
            current_biometrics = {b.id: b for b in user.biometrics}
            new_biometrics_list = []
            seen_indices = set()
            seen_fingers = set()

            for bio_data in biometrics_in:
                bio_id = bio_data.get('id') if isinstance(bio_data, dict) else bio_data.id
                sensor_idx = bio_data.get('sensor_index') if isinstance(bio_data, dict) else bio_data.sensor_index
                tmpl_data = bio_data.get('template_data') if isinstance(bio_data, dict) else bio_data.template_data
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
                    existing.finger_id = finger_id
                    new_biometrics_list.append(existing)
                else:
                    new_bio = UserBiometric(
                        sensor_index=sensor_idx,
                        template_data=tmpl_data,
                        finger_id=finger_id
                    )
                    new_biometrics_list.append(new_bio)

            user.biometrics = new_biometrics_list

        db.add(user)
        db.commit()
        db.refresh(user)

        new_data_raw = {}
        for field in tracked_fields:
            if hasattr(user, field):
                val = getattr(user, field)
                new_data_raw[field] = str(val) if val is not None else None
                
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

    def add_historical_schedule(self, db: Session, user_id: int, sch_data: dict, current_user_id: int) -> UserWorkScheduleConfig:
        user = user_repository.get(db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        valid_from = sch_data.get('valid_from')
        if not valid_from:
            valid_from = date.today()
            
        self._check_payroll_closure(db, valid_from, sch_data.get('valid_until'))
        
        new_sch = UserWorkScheduleConfig(
            user_id=user.id,
            day_of_week=sch_data.get('day_of_week'),
            daily_hours=sch_data.get('daily_hours'),
            entry_1=sch_data.get('entry_1'),
            exit_1=sch_data.get('exit_1'),
            entry_2=sch_data.get('entry_2'),
            exit_2=sch_data.get('exit_2'),
            valid_from=valid_from,
            valid_until=sch_data.get('valid_until')
        )
        db.add(new_sch)
        db.commit()
        db.refresh(new_sch)
        return new_sch

    def update_historical_schedule(self, db: Session, user_id: int, schedule_id: int, sch_data: dict, current_user_id: int) -> UserWorkScheduleConfig:
        sch = db.query(UserWorkScheduleConfig).filter(
            UserWorkScheduleConfig.id == schedule_id,
            UserWorkScheduleConfig.user_id == user_id
        ).first()
        if not sch:
            raise HTTPException(status_code=404, detail="Schedule not found")
            
        self._check_payroll_closure(db, sch.valid_from, sch.valid_until)
        
        valid_from = sch_data.get('valid_from', sch.valid_from)
        valid_until = sch_data.get('valid_until', sch.valid_until)
        self._check_payroll_closure(db, valid_from, valid_until)
        
        sch.day_of_week = sch_data.get('day_of_week', sch.day_of_week)
        sch.daily_hours = sch_data.get('daily_hours', sch.daily_hours)
        sch.entry_1 = sch_data.get('entry_1', sch.entry_1)
        sch.exit_1 = sch_data.get('exit_1', sch.exit_1)
        sch.entry_2 = sch_data.get('entry_2', sch.entry_2)
        sch.exit_2 = sch_data.get('exit_2', sch.exit_2)
        sch.valid_from = valid_from
        sch.valid_until = valid_until
        
        db.add(sch)
        db.commit()
        db.refresh(sch)
        return sch

    def delete_historical_schedule(self, db: Session, user_id: int, schedule_id: int, current_user_id: int):
        sch = db.query(UserWorkScheduleConfig).filter(
            UserWorkScheduleConfig.id == schedule_id,
            UserWorkScheduleConfig.user_id == user_id
        ).first()
        if not sch:
            raise HTTPException(status_code=404, detail="Schedule not found")
            
        self._check_payroll_closure(db, sch.valid_from, sch.valid_until)
        
        db.delete(sch)
        db.commit()


user_service = UserService()
