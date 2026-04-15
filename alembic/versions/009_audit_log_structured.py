import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

from alembic import op

revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = [col['name'] for col in inspector.get_columns('audit_logs')]

    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        if 'actor_name' not in columns:
            batch_op.add_column(sa.Column('actor_name', sa.String(), nullable=True))
        if 'target_user_id' not in columns:
            batch_op.add_column(sa.Column('target_user_id', sa.Integer(), nullable=True))
        if 'target_user_name' not in columns:
            batch_op.add_column(sa.Column('target_user_name', sa.String(), nullable=True))
        if 'justification' not in columns:
            batch_op.add_column(sa.Column('justification', sa.String(), nullable=True))
        if 'reason' not in columns:
            batch_op.add_column(sa.Column('reason', sa.String(), nullable=True))
        if 'record_time' not in columns:
            batch_op.add_column(sa.Column('record_time', sa.DateTime(timezone=True), nullable=True))
        if 'record_type' not in columns:
            batch_op.add_column(sa.Column('record_type', sa.String(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = [col['name'] for col in inspector.get_columns('audit_logs')]

    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        if 'record_type' in columns:
            batch_op.drop_column('record_type')
        if 'record_time' in columns:
            batch_op.drop_column('record_time')
        if 'reason' in columns:
            batch_op.drop_column('reason')
        if 'justification' in columns:
            batch_op.drop_column('justification')
        if 'target_user_name' in columns:
            batch_op.drop_column('target_user_name')
        if 'target_user_id' in columns:
            batch_op.drop_column('target_user_id')
        if 'actor_name' in columns:
            batch_op.drop_column('actor_name')
