import sqlalchemy as sa
from alembic import op

revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('user_biometrics', schema=None) as batch_op:
        batch_op.add_column(sa.Column('description', sa.String(), nullable=True))
        batch_op.alter_column('template_data',
               existing_type=sa.VARCHAR(),
               nullable=True)


def downgrade() -> None:
    with op.batch_alter_table('user_biometrics', schema=None) as batch_op:
        batch_op.alter_column('template_data',
               existing_type=sa.VARCHAR(),
               nullable=False)
        batch_op.drop_column('description')