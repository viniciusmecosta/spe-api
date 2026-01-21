"""add payroll closure and maintainer role

Revision ID: 003
Revises: 002
Create Date: 2024-01-02 00:00:00.000000

"""
import sqlalchemy as sa

from alembic import op

revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Cria tabela de fechamento de folha
    op.create_table('payroll_closures',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('month', sa.Integer(), nullable=False),
                    sa.Column('year', sa.Integer(), nullable=False),
                    sa.Column('is_closed', sa.Boolean(), nullable=False),
                    sa.Column('closed_by_user_id', sa.Integer(), nullable=False),
                    sa.Column('closed_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'),
                              nullable=True),
                    sa.ForeignKeyConstraint(['closed_by_user_id'], ['users.id'], ),
                    sa.PrimaryKeyConstraint('id'),
                    sa.UniqueConstraint('month', 'year', name='uq_payroll_month_year')
                    )
    op.create_index(op.f('ix_payroll_closures_id'), 'payroll_closures', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_payroll_closures_id'), table_name='payroll_closures')
    op.drop_table('payroll_closures')
