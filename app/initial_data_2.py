import logging
import random
from calendar import monthrange
from datetime import date, timedelta, datetime, time

from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.domain.models.enums import UserRole, RecordType
from app.repositories.time_record_repository import time_record_repository
from app.repositories.user_repository import user_repository
from app.schemas.user import UserCreate
from app.schemas.work_schedule import WorkScheduleCreate

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_antonio_data(db: Session) -> None:
    # 1. Dados do Usuário
    name = "Antonio Costa do Nasimento"
    username = "acosta"
    password = "Gabi2212"

    # Verifica se já existe
    user = user_repository.get_by_username(db, username=username)
    if not user:
        logger.info(f"Criando funcionário: {name}")

        # Cria escala padrão de 8h (Segunda a Sexta)
        schedules = [
            WorkScheduleCreate(day_of_week=i, daily_hours=8.0)
            for i in range(5)  # 0=Seg, 4=Sex
        ]

        user_in = UserCreate(
            name=name,
            username=username,
            password=password,
            role=UserRole.EMPLOYEE,
            is_active=True,
            schedules=schedules
        )

        user = user_repository.create(db, user_in)
        logger.info(f"Usuário {username} criado com sucesso (ID: {user.id}).")
    else:
        logger.info(f"Usuário {username} já existe (ID: {user.id}). Pulando criação.")

    # 2. Gerar Pontos para Novembro e Dezembro
    # Ano base: 2025 (conforme data atual do sistema)
    year = 2025
    months = [11, 12]

    logger.info("Iniciando geração de registros de ponto...")

    count_records = 0

    for month in months:
        # Obtém o último dia do mês
        _, last_day = monthrange(year, month)
        start_date = date(year, month, 1)
        end_date = date(year, month, last_day)

        current_day = start_date
        while current_day <= end_date:
            # Verifica se é dia útil (0=Segunda, 4=Sexta, 5=Sábado, 6=Domingo)
            if current_day.weekday() < 5:
                # Verifica se já tem ponto neste dia para não duplicar
                # Define o intervalo do dia para busca
                day_start = datetime.combine(current_day, time.min)
                day_end = datetime.combine(current_day, time.max)
                existing = time_record_repository.get_by_range(db, user.id, day_start, day_end)

                if not existing:
                    # Lógica de Horário: "De 7:30 a 8:30 horas por dia" (Duração)
                    # Entrada aleatória entre 07:50 e 08:10 para parecer natural
                    start_hour = 8
                    start_minute = random.randint(-10, 10)  # 07:50 a 08:10
                    entry_dt = datetime.combine(current_day, time(start_hour, 0)) + timedelta(minutes=start_minute)

                    # Duração aleatória entre 7h30min (450min) e 8h30min (510min)
                    worked_minutes = random.randint(450, 510)
                    exit_dt = entry_dt + timedelta(minutes=worked_minutes)

                    # Cria Entrada
                    time_record_repository.create(
                        db,
                        user_id=user.id,
                        record_type=RecordType.ENTRY,
                        record_datetime=entry_dt,
                        ip_address="127.0.0.1"
                    )

                    # Cria Saída
                    time_record_repository.create(
                        db,
                        user_id=user.id,
                        record_type=RecordType.EXIT,
                        record_datetime=exit_dt,
                        ip_address="127.0.0.1"
                    )

                    count_records += 1

            current_day += timedelta(days=1)

    logger.info(f"Concluído! {count_records} registros de entrada/saída criados para {name}.")


def main() -> None:
    db = SessionLocal()
    try:
        create_antonio_data(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()