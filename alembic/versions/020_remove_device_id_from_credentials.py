import sqlalchemy as sa
from alembic import op

revision = '020'
down_revision = '019'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('device_credentials') as batch_op:
        batch_op.drop_index('ix_device_credentials_device_id')
        batch_op.drop_column('device_id')


def downgrade():
    with op.batch_alter_table('device_credentials') as batch_op:
        batch_op.add_column(sa.Column('device_id', sa.String(), nullable=True))
        batch_op.create_index('ix_device_credentials_device_id', ['device_id'], unique=True)
