import sqlalchemy as sa

from alembic import op

revision = '040'
down_revision = '039'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('payroll_closures', sa.Column('report_path', sa.String(), nullable=True))


def downgrade():
    op.drop_column('payroll_closures', 'report_path')
