from alembic import op

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None

MINUTE_COLUMNS = (
    "worked_minutes",
    "accounted_minutes",
    "expected_minutes",
    "excess_minutes",
    "authorized_excess_minutes",
    "missing_minutes",
    "waiver_minutes",
)


def upgrade() -> None:
    op.execute(
        "ALTER TABLE time_records ALTER CONSTRAINT fk_time_records_original_record_id "
        "DEFERRABLE INITIALLY DEFERRED"
    )
    for column in MINUTE_COLUMNS:
        op.execute(
            f"ALTER TABLE daily_summaries ALTER COLUMN {column} "
            f"TYPE NUMERIC(14, 6) USING {column}::numeric"
        )


def downgrade() -> None:
    raise NotImplementedError(
        "A precisão dos resumos não pode ser reduzida sem perda de dados"
    )
