"""add is_time_verified to time_records

Revision ID: 005
Revises: 004
Create Date: 2025-09-03 12:00:00.000000

"""
import sqlalchemy as sa

from alembic import op

revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('time_records', sa.Column('is_time_verified', sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    with op.batch_alter_table('time_records') as batch_op:
        batch_op.drop_column('is_time_verified')
