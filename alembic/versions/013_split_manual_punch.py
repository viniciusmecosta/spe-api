import sqlalchemy as sa

from alembic import op

revision = '013'
down_revision = '012'
branch_labels = None
depends_on = None

def upgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('can_manual_punch_desktop', sa.Boolean(), server_default=sa.true(), nullable=True))
        batch_op.add_column(sa.Column('can_manual_punch_mobile', sa.Boolean(), server_default=sa.false(), nullable=True))

    op.execute("UPDATE users SET can_manual_punch_desktop = can_manual_punch")

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('can_manual_punch')

    with op.batch_alter_table('time_records', schema=None) as batch_op:
        batch_op.add_column(sa.Column('platform', sa.String(), nullable=True))

def downgrade() -> None:
    with op.batch_alter_table('time_records', schema=None) as batch_op:
        batch_op.drop_column('platform')

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('can_manual_punch', sa.Boolean(), server_default=sa.true(), nullable=True))

    op.execute("UPDATE users SET can_manual_punch = can_manual_punch_desktop")

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('can_manual_punch_desktop')
        batch_op.drop_column('can_manual_punch_mobile')