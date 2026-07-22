"""add deleted_at and deleted_by to adjustment_requests

Revision ID: 038
Revises: 037
Create Date: 2026-07-22 19:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '038'
down_revision = '037'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('adjustment_requests', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('adjustment_requests', sa.Column('deleted_by', sa.Integer(), nullable=True))
    with op.batch_alter_table('adjustment_requests', schema=None) as batch_op:
        batch_op.create_foreign_key('fk_adjustment_requests_deleted_by', 'users', ['deleted_by'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('adjustment_requests', schema=None) as batch_op:
        batch_op.drop_constraint('fk_adjustment_requests_deleted_by', type_='foreignkey')
        batch_op.drop_column('deleted_by')
        batch_op.drop_column('deleted_at')
