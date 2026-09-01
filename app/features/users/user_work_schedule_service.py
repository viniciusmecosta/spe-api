from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Annotated, Any, Dict, List

from fastapi import BackgroundTasks, Depends
from fastapi.encoders import jsonable_encoder
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.features.payroll.payroll_repository import (
    async_payroll_repository,
    payroll_repository,
)
from app.features.system.audit_service import audit_service
from app.features.users.user_exceptions import (
    BulkScheduleNotFoundError,
    BulkScheduleValidationError,
    ScheduleOverlapError,
    SchedulePayrollClosedError,
)
from app.features.users.user_models import User, UserWorkScheduleConfig
from app.features.users.user_repository import (
    async_user_repository,
    user_repository,
)
from app.shared import deps
from app.shared.daily_excess_service import daily_excess_service
from app.shared.enums import DayOfWeek


class UserWorkScheduleService:
    def __init__(
            self,
            db: Annotated[AsyncSession, Depends(deps.get_async_db)] = None,
    ):
        self.db = db

    @staticmethod
    def _parse_schedule_time(t_obj):
        if not t_obj:
            return None
        if isinstance(t_obj, time):
            return datetime.combine(date.today(), t_obj)
        if isinstance(t_obj, str):
            try:
                parts = t_obj.split(':')
                if len(parts) >= 2:
                    sec = int(parts[2]) if len(parts) > 2 else 0
                    return datetime.combine(date.today(), time(int(parts[0]), int(parts[1]), sec))
            except (ValueError, IndexError):
                return None
        return None

    @classmethod
    def _calculate_shift_seconds(cls, entry_time, exit_time) -> float:
        dt_entry = cls._parse_schedule_time(entry_time)
        dt_exit = cls._parse_schedule_time(exit_time)
        if not dt_entry or not dt_exit:
            return 0.0
        diff = (dt_exit - dt_entry).total_seconds()
        if diff < 0:
            diff += 24 * 3600
        return diff

    def _apply_schedule_updates(self, sch: UserWorkScheduleConfig, sch_data: dict, valid_from: date, valid_until: date):
        sch.day_of_week = sch_data.get('day_of_week', sch.day_of_week)
        sch.entry_1 = sch_data.get('entry_1', sch.entry_1)
        sch.exit_1 = sch_data.get('exit_1', sch.exit_1)
        sch.entry_2 = sch_data.get('entry_2', sch.entry_2)
        sch.exit_2 = sch_data.get('exit_2', sch.exit_2)
        sch.valid_from = valid_from
        sch.valid_until = valid_until
        sch.is_daily_excess_enabled = sch_data.get('is_daily_excess_enabled', True)

        total_seconds = (
                self._calculate_shift_seconds(sch.entry_1, sch.exit_1) +
                self._calculate_shift_seconds(sch.entry_2, sch.exit_2)
        )
        sch.daily_hours = round(total_seconds / 3600, 2)

    def _extract_schedule_data(self, sch: UserWorkScheduleConfig) -> dict:
        return {
            "day_of_week": sch.day_of_week,
            "daily_hours": sch.daily_hours,
            "valid_from": str(sch.valid_from) if sch.valid_from else None,
            "valid_until": str(sch.valid_until) if sch.valid_until else None,
            "entry_1": str(sch.entry_1) if sch.entry_1 else None,
            "exit_1": str(sch.exit_1) if sch.exit_1 else None,
            "entry_2": str(sch.entry_2) if sch.entry_2 else None,
            "exit_2": str(sch.exit_2) if sch.exit_2 else None
        }

    async def check_payroll_closure(self, db: Any, valid_from: date, valid_until: date = None):
        session = db if db is not None else self.db
        assert session is not None
        start_year = valid_from.year
        start_month = valid_from.month

        end_date = valid_until if valid_until else date.today()
        end_year = end_date.year
        end_month = end_date.month

        current_year = start_year
        current_month = start_month

        while (current_year < end_year) or (current_year == end_year and current_month <= end_month):
            if hasattr(session, "sync_session"):
                closure = await async_payroll_repository.get_by_month(session, current_month, current_year)
            else:
                closure = payroll_repository.get_by_month(session, current_month, current_year)
            if closure and closure.is_closed:
                raise SchedulePayrollClosedError(
                    f"Não é permitido alterar configurações de expediente. A folha de ponto de {current_month:02d}/{current_year} já está fechada."
                )
            current_month += 1
            if current_month > 12:
                current_month = 1
                current_year += 1

    def handle_schedule_overlap(self, user: User, day_of_week: int, valid_from: date, valid_until: date,
                                ignore_id: int = None):
        for sch in user.historical_schedules:
            if ignore_id and sch.id == ignore_id:
                continue
            if sch.day_of_week != day_of_week:
                continue

            sch_end = sch.valid_until if sch.valid_until else date.max
            new_end = valid_until if valid_until else date.max

            if sch.valid_from <= new_end and sch_end >= valid_from:
                raise ScheduleOverlapError()

    @staticmethod
    def _extract_schedule_item(cfg: UserWorkScheduleConfig) -> dict:
        return {
            "day_of_week": cfg.day_of_week,
            "daily_hours": cfg.daily_hours,
            "entry_1": cfg.entry_1,
            "exit_1": cfg.exit_1,
            "entry_2": cfg.entry_2,
            "exit_2": cfg.exit_2,
        }

    @staticmethod
    def _format_users_schedule_list(users_dict: dict) -> list[dict]:
        return [
            {"user_id": user_id, "schedules": sch_list}
            for user_id, sch_list in users_dict.items()
        ]

    async def get_bulk_schedules(self, db: Any | None = None, month: int = 0, year: int = 0) -> List[Dict[str, Any]]:
        session = db if db is not None else self.db
        assert session is not None
        start_of_month = date(year, month, 1)
        next_month = start_of_month.replace(day=28) + timedelta(days=4)
        end_of_month = next_month - timedelta(days=next_month.day)

        stmt = select(UserWorkScheduleConfig).where(
            UserWorkScheduleConfig.valid_from <= end_of_month,
            or_(
                UserWorkScheduleConfig.valid_until.is_(None),
                UserWorkScheduleConfig.valid_until >= start_of_month
            )
        )
        if hasattr(session, "sync_session"):
            configs = list((await session.scalars(stmt)).all())
        else:
            configs = session.query(UserWorkScheduleConfig).filter(
                UserWorkScheduleConfig.valid_from <= end_of_month,
                or_(
                    UserWorkScheduleConfig.valid_until == None,
                    UserWorkScheduleConfig.valid_until >= start_of_month
                )
            ).all()

        groups = defaultdict(lambda: defaultdict(list))
        for cfg in configs:
            key = (cfg.valid_from, cfg.valid_until)
            groups[key][cfg.user_id].append(self._extract_schedule_item(cfg))

        return [
            {
                "valid_from": v_from,
                "valid_until": v_until,
                "users": self._format_users_schedule_list(users_dict)
            }
            for (v_from, v_until), users_dict in groups.items()
        ]

    async def get_bulk_schedule(self, db: Any | None = None, valid_from: date = None, valid_until: date = None) -> Dict[
        str, Any]:
        session = db if db is not None else self.db
        assert session is not None
        stmt = select(UserWorkScheduleConfig).where(
            UserWorkScheduleConfig.valid_from == valid_from,
            UserWorkScheduleConfig.valid_until == valid_until
        )
        if hasattr(session, "sync_session"):
            configs = list((await session.scalars(stmt)).all())
        else:
            configs = session.query(UserWorkScheduleConfig).filter(
                UserWorkScheduleConfig.valid_from == valid_from,
                UserWorkScheduleConfig.valid_until == valid_until
            ).all()

        if not configs:
            raise BulkScheduleNotFoundError(valid_from=valid_from, valid_until=valid_until)

        users_dict = defaultdict(list)
        for cfg in configs:
            users_dict[cfg.user_id].append(self._extract_schedule_item(cfg))

        return {
            "valid_from": valid_from,
            "valid_until": valid_until,
            "users": self._format_users_schedule_list(users_dict)
        }

    def _process_single_user_bulk_add(self, user, schedules_in, valid_from, valid_until, errors, new_schedules):
        for sch_data_dict in schedules_in:
            day_of_week = sch_data_dict.get('day_of_week')
            day_name = DayOfWeek(day_of_week).nome
            try:
                self.handle_schedule_overlap(user, day_of_week, valid_from, valid_until)
            except (ScheduleOverlapError, Exception):
                errors.append(
                    f"Usuário {user.name} (ID: {user.id}) - {day_name}: Já existe um expediente vigente para esse dia informado.")
                continue
            new_sch = UserWorkScheduleConfig(user_id=user.id)
            self._apply_schedule_updates(new_sch, sch_data_dict, valid_from, valid_until)
            new_schedules.append(new_sch)

    async def _query_schedule_configs(self, session: Any, valid_from: date, valid_until: date) -> list[UserWorkScheduleConfig]:
        stmt = select(UserWorkScheduleConfig).where(
            UserWorkScheduleConfig.valid_from == valid_from,
            UserWorkScheduleConfig.valid_until == valid_until
        )
        if hasattr(session, "sync_session"):
            return list((await session.scalars(stmt)).all())
        return session.query(UserWorkScheduleConfig).filter(
            UserWorkScheduleConfig.valid_from == valid_from,
            UserWorkScheduleConfig.valid_until == valid_until
        ).all()

    async def _delete_schedule_configs(self, session: Any, configs: list[UserWorkScheduleConfig]) -> None:
        for cfg in configs:
            if hasattr(session, "delete"):
                if hasattr(session, "sync_session"):
                    await session.delete(cfg)
                else:
                    session.delete(cfg)

    async def _commit_and_audit_bulk(self, session: Any, current_user_id: int, action: str, old_data: dict = None, new_data: dict = None):
        if hasattr(session, "sync_session"):
            await session.commit()
            await audit_service.async_log_change(
                session, current_user_id, action,
                entity="USER_WORK_SCHEDULE_BULK", entity_id=0,
                old_data=old_data, new_data=new_data
            )
        else:
            session.commit()
            audit_service.log_change(
                session, current_user_id, action,
                entity="USER_WORK_SCHEDULE_BULK", entity_id=0,
                old_data=old_data, new_data=new_data
            )

    def _dispatch_user_ranges_bg(self, background_tasks: BackgroundTasks | None, user_ids: list[int], start_eval: date, end_eval: date):
        if not background_tasks or start_eval > end_eval:
            return
        for uid in user_ids:
            if uid:
                background_tasks.add_task(daily_excess_service.evaluate_user_range_bg, uid, start_eval, end_eval)

    async def bulk_add_schedules(self, db: Any | None = None, bulk_data: dict = None,
                                  current_user_id: int = 0,
                                  background_tasks: BackgroundTasks | None = None):
        session = db if db is not None else self.db
        assert session is not None
        valid_from = bulk_data.get('valid_from')
        valid_until = bulk_data.get('valid_until')

        if not valid_from or not valid_until:
            raise BulkScheduleValidationError("Data de início (valid_from) e fim (valid_until) são obrigatórias.")

        if (valid_until - valid_from).days > 31:
            raise BulkScheduleValidationError("A duração do expediente não pode ser superior a 1 mês.")

        users_input = bulk_data.get('users', [])
        if not users_input:
            raise BulkScheduleValidationError("Nenhum usuário informado.")

        await self.check_payroll_closure(session, valid_from, valid_until)

        errors = []
        new_schedules = []

        for user_data in users_input:
            uid = user_data.get('user_id')
            user = await async_user_repository.get(session, uid) if hasattr(session, "sync_session") else user_repository.get(session, uid)
            if not user:
                errors.append(f"Usuário com ID {uid} não encontrado.")
                continue
            self._process_single_user_bulk_add(user, user_data.get('schedules', []), valid_from, valid_until, errors, new_schedules)

        if errors:
            raise BulkScheduleValidationError(errors)

        for sch in new_schedules:
            session.add(sch)

        await self._commit_and_audit_bulk(
            session, current_user_id, "CREATE",
            new_data={"valid_from": str(valid_from), "valid_until": str(valid_until), "bulk_data": jsonable_encoder(bulk_data)}
        )

        self._dispatch_user_ranges_bg(background_tasks, [u.get('user_id') for u in users_input], valid_from, min(valid_until, date.today()))
        return {"message": f"{len(new_schedules)} expedientes criados com sucesso."}

    @staticmethod
    def _build_incoming_schedule_map(users_input: list[dict]) -> dict:
        incoming_map = {}
        for user_data in users_input:
            uid = user_data.get('user_id')
            for sch_data_dict in user_data.get('schedules', []):
                incoming_map[(uid, sch_data_dict.get('day_of_week'))] = sch_data_dict
        return incoming_map

    async def _collect_update_actions(self, session: Any, users_input: list[dict], existing_map: dict, new_valid_from: date, new_valid_until: date):
        to_update, to_create, errors = [], [], []
        for user_data in users_input:
            uid = user_data.get('user_id')
            user = await async_user_repository.get(session, uid) if hasattr(session, "sync_session") else user_repository.get(session, uid)
            if not user:
                errors.append(f"Usuário com ID {uid} não encontrado.")
                continue

            for sch_data in user_data.get('schedules', []):
                dow = sch_data.get('day_of_week')
                cfg = existing_map.get((uid, dow))
                try:
                    if cfg:
                        self.handle_schedule_overlap(user, dow, new_valid_from, new_valid_until, ignore_id=cfg.id)
                        to_update.append((cfg, sch_data))
                    else:
                        self.handle_schedule_overlap(user, dow, new_valid_from, new_valid_until)
                        to_create.append((user, sch_data))
                except ScheduleOverlapError as e:
                    errors.append(f"Usuário {user.name}: {str(e)}")
        return to_update, to_create, errors

    async def update_bulk_schedules(self, db: Any | None = None, old_valid_from: date = None,
                                    old_valid_until: date = None, bulk_data: dict = None,
                                    current_user_id: int = 0,
                                    background_tasks: BackgroundTasks | None = None):
        session = db if db is not None else self.db
        assert session is not None
        new_valid_from = bulk_data.get('valid_from')
        new_valid_until = bulk_data.get('valid_until')

        if not new_valid_from or not new_valid_until:
            raise BulkScheduleValidationError("Data de início (valid_from) e fim (valid_until) são obrigatórias.")

        if (new_valid_until - new_valid_from).days > 31:
            raise BulkScheduleValidationError("A duração do expediente não pode ser superior a 1 mês.")

        await self.check_payroll_closure(session, old_valid_from, old_valid_until)
        await self.check_payroll_closure(session, new_valid_from, new_valid_until)

        old_configs = await self._query_schedule_configs(session, old_valid_from, old_valid_until)
        existing_map = {(cfg.user_id, cfg.day_of_week): cfg for cfg in old_configs}
        users_input = bulk_data.get('users', [])
        incoming_map = self._build_incoming_schedule_map(users_input)

        to_delete = [cfg for key, cfg in existing_map.items() if key not in incoming_map]
        to_update, to_create, errors = await self._collect_update_actions(session, users_input, existing_map, new_valid_from, new_valid_until)

        if errors:
            raise BulkScheduleValidationError(errors)

        await self._delete_schedule_configs(session, to_delete)

        for cfg, new_data in to_update:
            self._apply_schedule_updates(cfg, new_data, new_valid_from, new_valid_until)
            session.add(cfg)

        for user, new_data in to_create:
            new_sch = UserWorkScheduleConfig(user_id=user.id)
            self._apply_schedule_updates(new_sch, new_data, new_valid_from, new_valid_until)
            session.add(new_sch)

        await self._commit_and_audit_bulk(
            session, current_user_id, "UPDATE",
            old_data={"valid_from": str(old_valid_from), "valid_until": str(old_valid_until)},
            new_data={"valid_from": str(new_valid_from), "valid_until": str(new_valid_until), "bulk_data": jsonable_encoder(bulk_data)}
        )

        all_uids = list({u[0] for u in existing_map.keys()} | {u.get('user_id') for u in users_input if u.get('user_id')})
        self._dispatch_user_ranges_bg(
            background_tasks, all_uids,
            min(old_valid_from, new_valid_from),
            min(max(old_valid_until, new_valid_until), date.today())
        )
        return {"message": "Expedientes atualizados com sucesso."}

    async def delete_bulk_schedules(self, db: Any | None = None, valid_from: date = None, valid_until: date = None,
                                    current_user_id: int = 0,
                                    background_tasks: BackgroundTasks | None = None):
        session = db if db is not None else self.db
        assert session is not None
        await self.check_payroll_closure(session, valid_from, valid_until)

        configs = await self._query_schedule_configs(session, valid_from, valid_until)
        if not configs:
            raise BulkScheduleNotFoundError(valid_from=valid_from, valid_until=valid_until)

        count = len(configs)
        all_uids = list({cfg.user_id for cfg in configs})

        await self._delete_schedule_configs(session, configs)

        await self._commit_and_audit_bulk(
            session, current_user_id, "DELETE",
            old_data={"valid_from": str(valid_from), "valid_until": str(valid_until), "count": count}
        )

        self._dispatch_user_ranges_bg(background_tasks, all_uids, valid_from, min(valid_until, date.today()))
        return {"message": f"{count} registros removidos com sucesso."}


user_work_schedule_service = UserWorkScheduleService()
