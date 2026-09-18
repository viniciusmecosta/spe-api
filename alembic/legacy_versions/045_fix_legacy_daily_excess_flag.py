from alembic import op

revision = '045'
down_revision = '044'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE user_work_schedule_configs SET is_daily_excess_enabled = FALSE WHERE valid_from < '2026-09-01'")


def downgrade():
    pass
