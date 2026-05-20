import sqlalchemy as sa
from alembic import op

revision = '025'
down_revision = '024'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table(
        'companies',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('cnpj', sa.String(), nullable=False),
        sa.Column('address', sa.String(), nullable=False),
        sa.Column('phone', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_companies_cnpj'), 'companies', ['cnpj'], unique=True)
    op.create_index(op.f('ix_companies_id'), 'companies', ['id'], unique=False)

def downgrade() -> None:
    op.drop_index(op.f('ix_companies_id'), table_name='companies')
    op.drop_index(op.f('ix_companies_cnpj'), table_name='companies')
    op.drop_table('companies')