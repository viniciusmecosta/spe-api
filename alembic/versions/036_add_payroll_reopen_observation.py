import sqlalchemy as sa
from alembic import op

revision = '036'
down_revision = '035'
branch_labels = None
depends_on = None

def upgrade() -> None:
    with op.batch_alter_table('payroll_closures', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reopen_observation', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('payroll_closures', schema=None) as batch_op:
        batch_op.drop_column('reopen_observation')
