from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest
from app.features.adjustments.adjustment_models import AdjustmentRequest
from app.features.reports.report_service import ReportService
from app.features.time_records.time_record_models import TimeRecord
from app.features.users.user_models import UserWorkScheduleConfig
from app.shared.daily_excess_service import DailyExcessService
from app.shared.enums import AdjustmentStatus, AdjustmentType, DayOfWeek, RecordType
from app.shared.time_calculation_service import TimeCalculationService


@pytest.fixture
def time_service():
    return TimeCalculationService()


@pytest.fixture
def excess_service():
    return DailyExcessService()


@pytest.fixture
def schedule_8h():
    return UserWorkScheduleConfig(
        id=1,
        user_id=1,
        day_of_week=DayOfWeek.SEGUNDA.value,
        daily_hours=8.0,
        entry_1=time(8, 0),
        exit_1=time(12, 0),
        entry_2=time(13, 0),
        exit_2=time(17, 0),
        is_daily_excess_enabled=True,
        valid_from=date(2026, 1, 1),
    )


def test_scenario_3_seconds_punch_no_excess(time_service, schedule_8h, excess_service):
    """Caso Funcionário 3: 2 batidas com 3s de diferença.
    Não há intervalo de almoço registrado. Excedente DEVE ser 0."""
    tz = ZoneInfo("America/Sao_Paulo")
    d = date(2026, 9, 2)
    dt1 = datetime(2026, 9, 2, 16, 33, 29, tzinfo=tz)
    dt2 = datetime(2026, 9, 2, 16, 33, 32, tzinfo=tz)
    r1 = TimeRecord(id=1, user_id=3, record_datetime=dt1, record_type=RecordType.ENTRY)
    r2 = TimeRecord(id=2, user_id=3, record_datetime=dt2, record_type=RecordType.EXIT)

    res = time_service.calculate_accounted_time([r1, r2], schedule_8h)
    assert res.total_excess_seconds == 0.0
    assert res.early_return_seconds == 0.0
    assert res.raw_seconds == 0.0  # Menos de 1 minuto arredonda para 0s em minutos
    assert res.accounted_seconds == 0.0

    adj = excess_service._create_daily_excess_adjustment(3, d, [r1, r2], res)
    assert adj is None


def test_scenario_8h_worked_30m_early_lunch_leaves_early(time_service, schedule_8h, excess_service):
    """Cenário: Trabalhou 8h brutas (08:00 às 12:00 = 4h, 12:30 às 16:30 = 4h).
    Voltou 30 min adiantado do almoço (almoço de 30m em vez de 1h).
    Tempo contabilizado pendente/rejeitado DEVE ser 7:30 (27.000s).
    Ajuste criado DEVE ser de 30min de almoço adiantado.
    Quando aprovado 30min, contabilizado DEVE voltar para 8:00 (28.800s)."""
    tz = ZoneInfo("America/Sao_Paulo")
    d = date(2026, 9, 2)
    r1 = TimeRecord(id=1, user_id=1, record_datetime=datetime(2026, 9, 2, 8, 0, tzinfo=tz), record_type=RecordType.ENTRY)
    r2 = TimeRecord(id=2, user_id=1, record_datetime=datetime(2026, 9, 2, 12, 0, tzinfo=tz), record_type=RecordType.EXIT)
    r3 = TimeRecord(id=3, user_id=1, record_datetime=datetime(2026, 9, 2, 12, 30, tzinfo=tz), record_type=RecordType.ENTRY)
    r4 = TimeRecord(id=4, user_id=1, record_datetime=datetime(2026, 9, 2, 16, 30, tzinfo=tz), record_type=RecordType.EXIT)
    records = [r1, r2, r3, r4]

    # 1. Sem ajuste ou com ajuste PENDING
    res_pending = time_service.calculate_accounted_time(records, schedule_8h, daily_excess_adj=None)
    assert res_pending.raw_seconds == 28800.0  # 8h
    assert res_pending.early_return_seconds == 1800.0  # 30m
    assert res_pending.total_excess_seconds == 1800.0  # 30m
    assert res_pending.accounted_seconds == 27000.0  # 7h30!

    adj = excess_service._create_daily_excess_adjustment(1, d, records, res_pending)
    assert adj is not None
    assert adj.amount_hours == 0.5
    assert "30min de almoço adiantado" in adj.reason_text
    assert "jornada excedente" not in adj.reason_text

    # 2. Com ajuste REJECTED
    adj_rej = AdjustmentRequest(status=AdjustmentStatus.REJECTED, amount_hours=0.5)
    res_rejected = time_service.calculate_accounted_time(records, schedule_8h, daily_excess_adj=adj_rej)
    assert res_rejected.accounted_seconds == 27000.0  # Permanece 7h30

    # 3. Com ajuste APPROVED
    adj_app = AdjustmentRequest(status=AdjustmentStatus.APPROVED, amount_hours=0.5, approved_amount_hours=0.5)
    res_approved = time_service.calculate_accounted_time(records, schedule_8h, daily_excess_adj=adj_app)
    assert res_approved.accounted_seconds == 28800.0  # Restaura para 8h00!


def test_scenario_9h30_worked_30m_early_lunch_1h_staying_late(time_service, schedule_8h, excess_service):
    """Cenário: Trabalhou 9h30 brutas (08:00 às 12:00 = 4h, 12:30 às 18:00 = 5h30).
    Excedente de 1h30 (90 min).
    30min de almoço adiantado e 60min de jornada excedente.
    Pendente/rejeitado: contabilizado = 8h00.
    Aprovado total (1.5h): contabilizado = 9h30.
    Aprovado parcial (1.0h): contabilizado = 9h00."""
    tz = ZoneInfo("America/Sao_Paulo")
    d = date(2026, 9, 2)
    r1 = TimeRecord(id=1, user_id=1, record_datetime=datetime(2026, 9, 2, 8, 0, tzinfo=tz), record_type=RecordType.ENTRY)
    r2 = TimeRecord(id=2, user_id=1, record_datetime=datetime(2026, 9, 2, 12, 0, tzinfo=tz), record_type=RecordType.EXIT)
    r3 = TimeRecord(id=3, user_id=1, record_datetime=datetime(2026, 9, 2, 12, 30, tzinfo=tz), record_type=RecordType.ENTRY)
    r4 = TimeRecord(id=4, user_id=1, record_datetime=datetime(2026, 9, 2, 18, 0, tzinfo=tz), record_type=RecordType.EXIT)
    records = [r1, r2, r3, r4]

    res_pending = time_service.calculate_accounted_time(records, schedule_8h, daily_excess_adj=None)
    assert res_pending.raw_seconds == 34200.0  # 9h30
    assert res_pending.excess_work_seconds == 5400.0  # 1h30 além de 8h
    assert res_pending.early_return_seconds == 1800.0  # 30m
    assert res_pending.total_excess_seconds == 5400.0  # 1h30 total
    assert res_pending.accounted_seconds == 28800.0  # 8h00

    adj = excess_service._create_daily_excess_adjustment(1, d, records, res_pending)
    assert adj is not None
    assert adj.amount_hours == 1.5
    assert "60min de jornada excedente" in adj.reason_text
    assert "30min de almoço adiantado" in adj.reason_text

    # Aprovado parcial (1h)
    adj_part = AdjustmentRequest(status=AdjustmentStatus.APPROVED, amount_hours=1.5, approved_amount_hours=1.0)
    res_part = time_service.calculate_accounted_time(records, schedule_8h, daily_excess_adj=adj_part)
    assert res_part.accounted_seconds == 32400.0  # 9h00

    # Aprovado total (1.5h)
    adj_full = AdjustmentRequest(status=AdjustmentStatus.APPROVED, amount_hours=1.5, approved_amount_hours=1.5)
    res_full = time_service.calculate_accounted_time(records, schedule_8h, daily_excess_adj=adj_full)
    assert res_full.accounted_seconds == 34200.0  # 9h30


def test_scenario_legacy_schedule_disabled(time_service):
    """Cenário: Escala com is_daily_excess_enabled = False (meses legados).
    Todo o tempo bruto é contabilizado, total_excess = 0."""
    legacy_sched = UserWorkScheduleConfig(
        id=2, user_id=1, day_of_week=DayOfWeek.SEGUNDA.value,
        daily_hours=8.0, is_daily_excess_enabled=False, valid_from=date(2026, 1, 1),
    )
    tz = ZoneInfo("America/Sao_Paulo")
    r1 = TimeRecord(id=1, user_id=1, record_datetime=datetime(2026, 7, 1, 8, 0, tzinfo=tz), record_type=RecordType.ENTRY)
    r2 = TimeRecord(id=2, user_id=1, record_datetime=datetime(2026, 7, 1, 18, 0, tzinfo=tz), record_type=RecordType.EXIT)
    records = [r1, r2]

    res = time_service.calculate_accounted_time(records, legacy_sched)
    assert res.raw_seconds == 36000.0  # 10h
    assert res.total_excess_seconds == 0.0
    assert res.accounted_seconds == 36000.0  # 10h integralmente contabilizadas


def test_scenario_multiple_punch_pairs_doctor_visit(time_service, schedule_8h):
    """Cenário: Saída intermediária para médico das 10:00 às 10:15.
    Almoço das 12:00 às 13:00.
    Sistema deve identificar corretamente o almoço às 12:00, e não a saída de 15min do médico."""
    tz = ZoneInfo("America/Sao_Paulo")
    r1 = TimeRecord(id=1, user_id=1, record_datetime=datetime(2026, 9, 2, 8, 0, tzinfo=tz), record_type=RecordType.ENTRY)
    r2 = TimeRecord(id=2, user_id=1, record_datetime=datetime(2026, 9, 2, 10, 0, tzinfo=tz), record_type=RecordType.EXIT)
    r3 = TimeRecord(id=3, user_id=1, record_datetime=datetime(2026, 9, 2, 10, 15, tzinfo=tz), record_type=RecordType.ENTRY)
    r4 = TimeRecord(id=4, user_id=1, record_datetime=datetime(2026, 9, 2, 12, 0, tzinfo=tz), record_type=RecordType.EXIT)
    r5 = TimeRecord(id=5, user_id=1, record_datetime=datetime(2026, 9, 2, 13, 0, tzinfo=tz), record_type=RecordType.ENTRY)
    r6 = TimeRecord(id=6, user_id=1, record_datetime=datetime(2026, 9, 2, 17, 15, tzinfo=tz), record_type=RecordType.EXIT)
    records = [r1, r2, r3, r4, r5, r6]

    has_rule, excess_lunch, early_return = time_service._compute_lunch_metrics(records, schedule_8h)
    assert has_rule is True
    assert excess_lunch == 0.0
    assert early_return == 0.0  # Almoço foi de 12:00 às 13:00 (exatamente 1h)


def test_period_time_unapproved_excess_deducted_from_balance(time_service, schedule_8h):
    """Cenário: calculate_period_time com excedente rejeitado.
    O excedente rejeitado de 2h DEVE ser computado em unapproved_extra_seconds.
    extra_seconds DEVE ser 0.0 e final_balance DEVE ser 0.0."""
    tz = ZoneInfo("America/Sao_Paulo")
    d = date(2026, 9, 1)
    r1 = TimeRecord(id=1, user_id=1, record_datetime=datetime(2026, 9, 1, 8, 0, tzinfo=tz), record_type=RecordType.ENTRY)
    r2 = TimeRecord(id=2, user_id=1, record_datetime=datetime(2026, 9, 1, 18, 0, tzinfo=tz), record_type=RecordType.EXIT)
    records = [r1, r2]

    adj_rej = AdjustmentRequest(
        id=10, user_id=1, target_date=d, adjustment_type=AdjustmentType.DAILY_EXCESS,
        status=AdjustmentStatus.REJECTED, amount_hours=2.0
    )

    schedule_8h.day_of_week = DayOfWeek.from_date(d).value
    period_res = time_service.calculate_period_time(
        start_date=d, end_date=d, records=records, adjustments=[adj_rej],
        holidays=[], historical_schedules=[schedule_8h]
    )

    daily_res = period_res.daily_results[d]
    assert daily_res.gross_worked_seconds == 36000.0  # 10h bruto
    assert daily_res.unapproved_extra_seconds == 7200.0  # 2h não autorizadas
    assert daily_res.net_worked_seconds == 28800.0  # 8h líquido
    assert daily_res.extra_seconds == 0.0  # 0h extras no saldo
    assert period_res.total_extra_seconds == 0.0
    assert period_res.total_accounted_seconds == 28800.0  # 8h contabilizadas


def test_report_service_includes_daily_excess_in_adjustments_list():
    rs = ReportService()
    d = date(2026, 9, 1)
    adj_pending = AdjustmentRequest(id=1, adjustment_type=AdjustmentType.DAILY_EXCESS, status=AdjustmentStatus.PENDING, target_date=d)
    adj_approved = AdjustmentRequest(id=2, adjustment_type=AdjustmentType.DAILY_EXCESS, status=AdjustmentStatus.APPROVED, target_date=d)

    day_adjs = rs._build_day_adjustments_list([adj_pending, adj_approved], d)
    assert len(day_adjs) == 2
    assert day_adjs[0].id == 1
    assert day_adjs[1].id == 2
