import sqlalchemy as sa

from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user_work_schedule_configs", sa.Column("daily_minutes", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE user_work_schedule_configs SET daily_minutes = "
        "CAST(ROUND(CAST(daily_hours AS NUMERIC) * 60) AS INTEGER)"
    )
    op.alter_column("user_work_schedule_configs", "daily_minutes", nullable=False)
    op.drop_column("user_work_schedule_configs", "daily_hours")


def downgrade():
    op.add_column("user_work_schedule_configs", sa.Column("daily_hours", sa.Float(), nullable=True))
    op.execute("UPDATE user_work_schedule_configs SET daily_hours = daily_minutes / 60.0")
    op.alter_column("user_work_schedule_configs", "daily_hours", nullable=False)
    op.drop_column("user_work_schedule_configs", "daily_minutes")
