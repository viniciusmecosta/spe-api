from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE UNIQUE INDEX uq_payroll_closures_active_period "
        "ON payroll_closures (year, month) "
        "WHERE deleted_at IS NULL AND is_closed = TRUE"
    )


def downgrade() -> None:
    op.execute("DROP INDEX uq_payroll_closures_active_period")
