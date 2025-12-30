"""add amount_hours to adjustment_requests

Revision ID: 004
Revises: 003
Create Date: 2025-09-03 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# Identificadores da revisão
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Adiciona a coluna amount_hours na tabela adjustment_requests
    op.add_column('adjustment_requests', sa.Column('amount_hours', sa.Float(), nullable=True))

def downgrade() -> None:
    # Remove a coluna caso precise desfazer (com suporte a SQLite via batch)
    with op.batch_alter_table('adjustment_requests') as batch_op:
        batch_op.drop_column('amount_hours')