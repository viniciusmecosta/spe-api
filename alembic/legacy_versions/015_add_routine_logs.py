import sqlalchemy as sa

from alembic import op

revision = '015'
down_revision = '014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'routine_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('routine_type', sa.String(), nullable=False),
        sa.Column('execution_time', sa.DateTime(), nullable=False),
        sa.Column('target_date', sa.Date(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('details', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_routine_logs_id'), 'routine_logs', ['id'], unique=False)
    op.create_index(op.f('ix_routine_logs_routine_type'), 'routine_logs', ['routine_type'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_routine_logs_routine_type'), table_name='routine_logs')
    op.drop_index(op.f('ix_routine_logs_id'), table_name='routine_logs')
    op.drop_table('routine_logs')
