import sqlalchemy as sa
from alembic import op

revision = '032'
down_revision = '031'
branch_labels = None
depends_on = None

def upgrade() -> None:
    with op.batch_alter_table('payroll_closures') as batch_op:
        batch_op.add_column(sa.Column('deleted_at', sa.TIMESTAMP(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('deleted_by', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_payroll_closures_deleted_by_users', 'users', ['deleted_by'], ['id'])
        batch_op.drop_constraint('uq_payroll_month_year', type_='unique')

def downgrade() -> None:
    with op.batch_alter_table('payroll_closures') as batch_op:
        batch_op.create_unique_constraint('uq_payroll_month_year', ['month', 'year'])
        batch_op.drop_constraint('fk_payroll_closures_deleted_by_users', type_='foreignkey')
        batch_op.drop_column('deleted_by')
        batch_op.drop_column('deleted_at')
