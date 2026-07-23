"""add is_tolerance_exempt

Revision ID: 039
Revises: 038
Create Date: 2026-07-23 09:28:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '039'
down_revision = '038'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('is_tolerance_exempt', sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade():
    op.drop_column('users', 'is_tolerance_exempt')
