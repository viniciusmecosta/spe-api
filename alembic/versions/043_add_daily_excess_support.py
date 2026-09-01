from alembic import op
import sqlalchemy as sa

revision = '043'
down_revision = '042'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('adjustment_requests', schema=None) as batch_op:
        batch_op.add_column(sa.Column('approved_amount_hours', sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table('adjustment_requests', schema=None) as batch_op:
        batch_op.drop_column('approved_amount_hours')
