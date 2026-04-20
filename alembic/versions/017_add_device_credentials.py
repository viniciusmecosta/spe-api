import sqlalchemy as sa

from alembic import op

revision = '017'
down_revision = '016'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table('device_credentials',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('device_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
                    sa.Column('key_type', sa.Enum('DEVICE', 'CONSUMER', name='devicekeytype'), server_default='DEVICE',
                              nullable=False),
        sa.Column('api_key_hash', sa.String(), nullable=False),
                    sa.Column('is_active', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_device_credentials_device_id'), 'device_credentials', ['device_id'], unique=True)
    op.create_index(op.f('ix_device_credentials_id'), 'device_credentials', ['id'], unique=False)

def downgrade() -> None:
    op.drop_index(op.f('ix_device_credentials_id'), table_name='device_credentials')
    op.drop_index(op.f('ix_device_credentials_device_id'), table_name='device_credentials')
    op.drop_table('device_credentials')