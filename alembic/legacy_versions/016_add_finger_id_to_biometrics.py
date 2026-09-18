import sqlalchemy as sa

from alembic import op

revision = '016'
down_revision = '015'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('user_biometrics', schema=None) as batch_op:
        batch_op.add_column(sa.Column('finger_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('user_biometrics', schema=None) as batch_op:
        batch_op.drop_column('finger_id')
