import sqlalchemy as sa

from alembic import op

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "schedule_hours_archive",
        sa.Column(
            "schedule_id",
            sa.Integer(),
            sa.ForeignKey("user_work_schedule_configs.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("daily_hours", sa.Float(), nullable=False),
        sa.Column("migrated_minutes", sa.Integer(), nullable=False),
    )
    op.execute(
        "INSERT INTO schedule_hours_archive (schedule_id, daily_hours, migrated_minutes) "
        "SELECT id, daily_hours, CAST(ROUND(CAST(daily_hours AS NUMERIC) * 60) AS INTEGER) "
        "FROM user_work_schedule_configs"
    )
    op.add_column("user_work_schedule_configs", sa.Column("daily_minutes", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE user_work_schedule_configs SET daily_minutes = "
        "(SELECT migrated_minutes FROM schedule_hours_archive "
        "WHERE schedule_id = user_work_schedule_configs.id)"
    )
    op.alter_column("user_work_schedule_configs", "daily_minutes", nullable=False)
    op.drop_column("user_work_schedule_configs", "daily_hours")


def downgrade():
    op.add_column("user_work_schedule_configs", sa.Column("daily_hours", sa.Float(), nullable=True))
    op.execute(
        "UPDATE user_work_schedule_configs SET daily_hours = COALESCE("
        "(SELECT daily_hours FROM schedule_hours_archive "
        "WHERE schedule_id = user_work_schedule_configs.id "
        "AND migrated_minutes = user_work_schedule_configs.daily_minutes), "
        "daily_minutes / 60.0)"
    )
    op.alter_column("user_work_schedule_configs", "daily_hours", nullable=False)
    op.drop_column("user_work_schedule_configs", "daily_minutes")
    op.drop_table("schedule_hours_archive")
