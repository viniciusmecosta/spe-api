import sqlalchemy as sa

from alembic import op

revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('adjustment_requests', sa.Column('amount_hours', sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('adjustment_requests') as batch_op:
        batch_op.drop_column('amount_hours')
