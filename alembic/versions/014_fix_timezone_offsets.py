from alembic import op

revision = '014'
down_revision = '013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE time_records SET created_at = created_at - INTERVAL '3 hours' WHERE created_at IS NOT NULL;")
    op.execute("UPDATE time_records SET updated_at = updated_at - INTERVAL '3 hours' WHERE updated_at IS NOT NULL;")
    try:
        op.execute(
            "UPDATE manual_adjustments SET adjusted_at = adjusted_at - INTERVAL '3 hours' WHERE adjusted_at IS NOT NULL;")
    except Exception:
        pass
    op.execute("UPDATE audit_logs SET timestamp = timestamp - INTERVAL '3 hours' WHERE timestamp IS NOT NULL;")
    op.execute("UPDATE payroll_closures SET closed_at = closed_at - INTERVAL '3 hours' WHERE closed_at IS NOT NULL;")
    op.execute("UPDATE user_biometrics SET created_at = created_at - INTERVAL '3 hours' WHERE created_at IS NOT NULL;")
    op.execute("UPDATE users SET created_at = created_at - INTERVAL '3 hours' WHERE created_at IS NOT NULL;")
    op.execute("UPDATE users SET updated_at = updated_at - INTERVAL '3 hours' WHERE updated_at IS NOT NULL;")
    op.execute(
        "UPDATE adjustment_requests SET created_at = created_at - INTERVAL '3 hours' WHERE created_at IS NOT NULL;")
    op.execute(
        "UPDATE adjustment_requests SET reviewed_at = reviewed_at - INTERVAL '3 hours' WHERE reviewed_at IS NOT NULL;")
    op.execute(
        "UPDATE adjustment_attachments SET uploaded_at = uploaded_at - INTERVAL '3 hours' WHERE uploaded_at IS NOT NULL;")


def downgrade() -> None:
    op.execute("UPDATE time_records SET created_at = created_at + INTERVAL '3 hours' WHERE created_at IS NOT NULL;")
    op.execute("UPDATE time_records SET updated_at = updated_at + INTERVAL '3 hours' WHERE updated_at IS NOT NULL;")
    try:
        op.execute(
            "UPDATE manual_adjustments SET adjusted_at = adjusted_at + INTERVAL '3 hours' WHERE adjusted_at IS NOT NULL;")
    except Exception:
        pass
    op.execute("UPDATE audit_logs SET timestamp = timestamp + INTERVAL '3 hours' WHERE timestamp IS NOT NULL;")
    op.execute("UPDATE payroll_closures SET closed_at = closed_at + INTERVAL '3 hours' WHERE closed_at IS NOT NULL;")
    op.execute("UPDATE user_biometrics SET created_at = created_at + INTERVAL '3 hours' WHERE created_at IS NOT NULL;")
    op.execute("UPDATE users SET created_at = created_at + INTERVAL '3 hours' WHERE created_at IS NOT NULL;")
    op.execute("UPDATE users SET updated_at = updated_at + INTERVAL '3 hours' WHERE updated_at IS NOT NULL;")
    op.execute(
        "UPDATE adjustment_requests SET created_at = created_at + INTERVAL '3 hours' WHERE created_at IS NOT NULL;")
    op.execute(
        "UPDATE adjustment_requests SET reviewed_at = reviewed_at + INTERVAL '3 hours' WHERE reviewed_at IS NOT NULL;")
    op.execute(
        "UPDATE adjustment_attachments SET uploaded_at = uploaded_at + INTERVAL '3 hours' WHERE uploaded_at IS NOT NULL;")
