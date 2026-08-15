from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

revision = '037'
down_revision = '036'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    tables = inspector.get_table_names()

    with op.batch_alter_table('time_records', schema=None) as batch_op:
        batch_op.add_column(sa.Column('is_verified', sa.Boolean(), server_default=sa.true(), nullable=False))

    if 'user_work_schedule_configs' not in tables:
        op.create_table(
            'user_work_schedule_configs',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('day_of_week', sa.Integer(), nullable=False),
            sa.Column('daily_hours', sa.Float(), nullable=False),
            sa.Column('entry_1', sa.Time(), nullable=True),
            sa.Column('exit_1', sa.Time(), nullable=True),
            sa.Column('entry_2', sa.Time(), nullable=True),
            sa.Column('exit_2', sa.Time(), nullable=True),
            sa.Column('valid_from', sa.Date(), nullable=False),
            sa.Column('valid_until', sa.Date(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
            sa.PrimaryKeyConstraint('id')
        )
        op.create_index(op.f('ix_user_work_schedule_configs_id'), 'user_work_schedule_configs', ['id'], unique=False)

    if 'work_schedules' in tables and 'user_work_schedule_configs' in tables:
        op.execute(
            """
            INSERT INTO user_work_schedule_configs (user_id, day_of_week, daily_hours, valid_from, valid_until)
            SELECT user_id, day_of_week, daily_hours, '2000-01-01', NULL 
            FROM work_schedules;
            """
        )

    if 'work_schedules' in tables:
        op.drop_table('work_schedules')


def downgrade() -> None:
    op.create_table('work_schedules',
        sa.Column('id', sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column('day_of_week', sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column('daily_hours', sa.FLOAT(), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='work_schedules_user_id_fkey'),
        sa.PrimaryKeyConstraint('id', name='work_schedules_pkey')
    )
    
    op.execute(
        """
        INSERT INTO work_schedules (user_id, day_of_week, daily_hours)
        SELECT user_id, day_of_week, daily_hours
        FROM user_work_schedule_configs
        WHERE valid_until IS NULL OR valid_until >= CURRENT_DATE;
        """
    )
    
    op.drop_index(op.f('ix_user_work_schedule_configs_id'), table_name='user_work_schedule_configs')
    op.drop_table('user_work_schedule_configs')

    with op.batch_alter_table('time_records', schema=None) as batch_op:
        batch_op.drop_column('is_verified')
