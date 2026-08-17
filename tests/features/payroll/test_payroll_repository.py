from app.features.payroll.payroll_repository import PayrollRepository


def test_payroll_repository(db_session, normal_user):
    repo = PayrollRepository()

    created = repo.create(db_session, month=11, year=2026, user_id=normal_user.id)
    assert created.id is not None

    by_month = repo.get_by_month(db_session, 11, 2026)
    assert by_month.id == created.id

    all_res = repo.get_all(db_session, year=2026)
    assert len(all_res) >= 1

    hist = repo.get_history(db_session, 11, 2026)
    assert len(hist) >= 1

    repo.delete(db_session, 11, 2026, user_id=normal_user.id, observation="Reopened test")
    assert repo.get_by_month(db_session, 11, 2026) is None
