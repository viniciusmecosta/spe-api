import sqlalchemy as sa
from alembic import op

revision = '028'
down_revision = '027'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('time_records', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('time_records', sa.Column('deleted_by', sa.Integer(), sa.ForeignKey('users.id'), nullable=True))
    op.add_column('time_records', sa.Column('is_ignored', sa.Boolean(), nullable=False, server_default=sa.text('0')))


def downgrade() -> None:
    with op.batch_alter_table('time_records') as batch_op:
        batch_op.drop_column('is_ignored')
        batch_op.drop_column('deleted_by')
        batch_op.drop_column('deleted_at')
