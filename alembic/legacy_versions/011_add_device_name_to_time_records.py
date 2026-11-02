import sqlalchemy as sa

from alembic import op

revision = '011'
down_revision = '010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('time_records', sa.Column('device_name', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('time_records') as batch_op:
        batch_op.drop_column('device_name')
