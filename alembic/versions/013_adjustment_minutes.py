import sqlalchemy as sa

from alembic import op

revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("adjustment_requests", sa.Column("amount_minutes", sa.Integer(), nullable=True))
    op.add_column("adjustment_requests", sa.Column("approved_amount_minutes", sa.Integer(), nullable=True))
    op.execute(
        "UPDATE adjustment_requests SET "
        "amount_minutes = CAST(ROUND(CAST(amount_hours AS NUMERIC) * 60) AS INTEGER), "
        "approved_amount_minutes = CAST(ROUND(CAST(approved_amount_hours AS NUMERIC) * 60) AS INTEGER)"
    )
    op.drop_column("adjustment_requests", "amount_hours")
    op.drop_column("adjustment_requests", "approved_amount_hours")


def downgrade():
    op.add_column("adjustment_requests", sa.Column("amount_hours", sa.Float(), nullable=True))
    op.add_column("adjustment_requests", sa.Column("approved_amount_hours", sa.Float(), nullable=True))
    op.execute(
        "UPDATE adjustment_requests SET amount_hours = amount_minutes / 60.0, "
        "approved_amount_hours = approved_amount_minutes / 60.0"
    )
    op.drop_column("adjustment_requests", "amount_minutes")
    op.drop_column("adjustment_requests", "approved_amount_minutes")
