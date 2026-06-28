import sqlalchemy as sa

from alembic import op

revision = '027'
down_revision = '026'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'firmwares',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('version', sa.String(), nullable=False),
        sa.Column('file_path', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_firmwares_id'), 'firmwares', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_firmwares_id'), table_name='firmwares')
    op.drop_table('firmwares')