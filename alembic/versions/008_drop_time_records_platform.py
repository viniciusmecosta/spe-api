import sqlalchemy as sa

from alembic import op

revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column('time_records', 'platform')
    op.drop_column('time_records', 'is_verified')


def downgrade():
    op.add_column(
        'time_records',
        sa.Column('is_verified', sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column('time_records', sa.Column('platform', sa.String(), nullable=True))
