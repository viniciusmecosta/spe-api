import sqlalchemy as sa
from alembic import op

revision = '019'
down_revision = '018'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table('manual_authorizations')


def downgrade():
    op.create_table(
        'manual_authorizations',
        sa.Column('id', sa.Integer(), primary_key=True, index=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('authorized_by_id', sa.Integer(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('start_time', sa.DateTime(), nullable=False),
        sa.Column('end_time', sa.DateTime(), nullable=False),
        sa.Column('reason', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True)
    )
