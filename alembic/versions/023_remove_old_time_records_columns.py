import sqlalchemy as sa
from alembic import op

revision = '023'
down_revision = '022'
branch_labels = None
depends_on = None

def upgrade() -> None:
    with op.batch_alter_table('time_records', schema=None) as batch_op:
        batch_op.drop_column('original_timestamp')
        batch_op.drop_column('is_time_verified')
        batch_op.drop_column('is_manual')


def downgrade() -> None:
    with op.batch_alter_table('time_records', schema=None) as batch_op:
        batch_op.add_column(sa.Column('original_timestamp', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('is_time_verified', sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column('is_manual', sa.Boolean(), nullable=True))