"""Create printers and add auto print settings

Revision ID: 042
Revises: 041
Create Date: 2026-08-10 13:58:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '042'
down_revision = '041'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        'printers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('address', sa.String(), nullable=False),
        sa.Column('status', sa.Boolean(), server_default='1', nullable=False),
        sa.Column('paper_width', sa.Integer(), server_default='80', nullable=False),
        sa.Column('company_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_printers_id'), 'printers', ['id'], unique=False)

    with op.batch_alter_table('companies', schema=None) as batch_op:
        batch_op.add_column(sa.Column('auto_print_receipt', sa.Boolean(), server_default='0', nullable=False))
        batch_op.add_column(sa.Column('default_printer_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_companies_default_printer_id', 'printers', ['default_printer_id'], ['id'])

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('auto_print_receipt', sa.Boolean(), nullable=True))

def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('auto_print_receipt')

    with op.batch_alter_table('companies', schema=None) as batch_op:
        batch_op.drop_constraint('fk_companies_default_printer_id', type_='foreignkey')
        batch_op.drop_column('default_printer_id')
        batch_op.drop_column('auto_print_receipt')

    op.drop_index(op.f('ix_printers_id'), table_name='printers')
    op.drop_table('printers')
