"""drop manual_adjustments table

Revision ID: 029_drop_manual_adjustments
Revises: 028_add_audit_fields
Create Date: 2026-06-29 14:02:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision = '029_drop_manual_adjustments'
down_revision = '028_add_audit_fields'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    tables = inspector.get_table_names()
    
    if 'manual_adjustments' in tables:
        op.drop_table('manual_adjustments')


def downgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    tables = inspector.get_table_names()
    
    if 'manual_adjustments' not in tables:
        op.create_table(
            'manual_adjustments',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('time_record_id', sa.Integer(), nullable=False),
            sa.Column('previous_type', sa.String(length=10), nullable=False),
            sa.Column('new_type', sa.String(length=10), nullable=False),
            sa.Column('adjusted_by_user_id', sa.Integer(), nullable=False),
            sa.Column('adjusted_at', sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(['adjusted_by_user_id'], ['users.id'], ),
            sa.ForeignKeyConstraint(['time_record_id'], ['time_records.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_manual_adjustments_id'), 'manual_adjustments', ['id'], unique=False)
