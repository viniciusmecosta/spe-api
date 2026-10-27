from alembic import op
import sqlalchemy as sa

revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column('time_records', 'platform')


def downgrade():
    op.add_column('time_records', sa.Column('platform', sa.String(), nullable=True))
