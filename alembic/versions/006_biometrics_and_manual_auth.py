"""biometrics and manual auth

Revision ID: 006
Revises: 005
Create Date: 2024-03-16 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'user_biometrics',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('sensor_index', sa.Integer(), nullable=False),
        sa.Column('template_data', sa.Text(), nullable=False),
        sa.Column('label', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sensor_index')
    )
    op.create_index(op.f('ix_user_biometrics_id'), 'user_biometrics', ['id'], unique=False)

    # Create manual_punch_authorizations table
    op.create_table(
        'manual_punch_authorizations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('authorized_by', sa.Integer(), nullable=False),
        sa.Column('valid_from', sa.DateTime(), nullable=False),
        sa.Column('valid_until', sa.DateTime(), nullable=False),
        sa.Column('reason', sa.String(), nullable=False),
        sa.ForeignKeyConstraint(['authorized_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_manual_punch_authorizations_id'), 'manual_punch_authorizations', ['id'], unique=False)

    op.add_column('time_records', sa.Column('biometric_id', sa.Integer(), nullable=True))
    op.create_foreign_key(None, 'time_records', 'user_biometrics', ['biometric_id'], ['id'])


def downgrade():
    op.drop_constraint(None, 'time_records', type_='foreignkey')
    op.drop_column('time_records', 'biometric_id')
    op.drop_index(op.f('ix_manual_punch_authorizations_id'), table_name='manual_punch_authorizations')
    op.drop_table('manual_punch_authorizations')
    op.drop_index(op.f('ix_user_biometrics_id'), table_name='user_biometrics')
    op.drop_table('user_biometrics')