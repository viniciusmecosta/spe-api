from alembic import op
import sqlalchemy as sa

revision = '044'
down_revision = '043'
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table('user_work_schedule_configs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_daily_excess_enabled', sa.Boolean(), nullable=True, server_default='1'))

def downgrade():
    with op.batch_alter_table('user_work_schedule_configs', schema=None) as batch_op:
        batch_op.drop_column('is_daily_excess_enabled')
