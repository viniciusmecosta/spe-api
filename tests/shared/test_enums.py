from app.shared.enums import DayOfWeek, UserRole, RecordType, AdjustmentType, AdjustmentStatus, DeviceKeyType


def test_day_of_week_sigla_and_props():
    seg = DayOfWeek.SEGUNDA
    assert seg.sigla == "Seg"
    assert DayOfWeek.TERCA.sigla == "Ter"
    assert DayOfWeek.QUARTA.sigla == "Qua"
    assert DayOfWeek.QUINTA.sigla == "Qui"
    assert DayOfWeek.SEXTA.sigla == "Sex"
    assert DayOfWeek.SABADO.sigla == "Sáb"
    assert DayOfWeek.DOMINGO.sigla == "Dom"

    assert seg.nome == "Segunda-feira"
    assert seg.abreviado == "Segunda"
