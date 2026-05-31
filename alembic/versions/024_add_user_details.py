import sqlalchemy as sa
from alembic import op

revision = '024'
down_revision = '023'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('cpf', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('email', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('pis', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('endereco', sa.String(), nullable=True))
        batch_op.create_index(batch_op.f('ix_users_cpf'), ['cpf'], unique=True)
        batch_op.create_index(batch_op.f('ix_users_email'), ['email'], unique=True)


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_email'))
        batch_op.drop_index(batch_op.f('ix_users_cpf'))
        batch_op.drop_column('endereco')
        batch_op.drop_column('pis')
        batch_op.drop_column('email')
        batch_op.drop_column('cpf')
