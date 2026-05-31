import sqlalchemy as sa

from alembic import op

revision = '022'
down_revision = '021'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('user_biometrics', schema=None) as batch_op:
        batch_op.drop_column('description')


def downgrade() -> None:
    with op.batch_alter_table('user_biometrics', schema=None) as batch_op:
        batch_op.add_column(sa.Column('description', sa.String(), nullable=True))
