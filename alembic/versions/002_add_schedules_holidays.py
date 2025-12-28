import sqlalchemy as sa

from alembic import op

revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('work_schedules',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('user_id', sa.Integer(), nullable=False),
                    sa.Column('day_of_week', sa.Integer(), nullable=False),
                    sa.Column('daily_hours', sa.Float(), nullable=False),
                    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
                    sa.PrimaryKeyConstraint('id')
                    )
    op.create_index(op.f('ix_work_schedules_id'), 'work_schedules', ['id'], unique=False)

    # Holidays
    op.create_table('holidays',
                    sa.Column('id', sa.Integer(), nullable=False),
                    sa.Column('date', sa.Date(), nullable=False),
                    sa.Column('name', sa.String(), nullable=False),
                    sa.PrimaryKeyConstraint('id'),
                    sa.UniqueConstraint('date')
                    )
    op.create_index(op.f('ix_holidays_id'), 'holidays', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_holidays_id'), table_name='holidays')
    op.drop_table('holidays')
    op.drop_index(op.f('ix_work_schedules_id'), table_name='work_schedules')
    op.drop_table('work_schedules')
