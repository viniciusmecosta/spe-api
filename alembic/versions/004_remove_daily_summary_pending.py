from alembic import op


revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_daily_summaries_pending")
    op.execute("ALTER TABLE daily_summaries DROP COLUMN IF EXISTS pending_recalculation")


def downgrade() -> None:
    pass
