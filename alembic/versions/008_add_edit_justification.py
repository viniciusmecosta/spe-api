import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

from alembic import op

revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = [col['name'] for col in inspector.get_columns('time_records')]

    with op.batch_alter_table('time_records', schema=None) as batch_op:
        if 'edit_justification' not in columns:
            batch_op.add_column(sa.Column('edit_justification',
                                          sa.Enum('FORGOT_ENTRY', 'FORGOT_EXIT', 'SYSTEM_ERROR', 'INITIAL_INCLUSION',
                                                  'INITIAL_EDIT', 'REGISTRATION_MISTAKE', 'IRRELEVANT_RECORD', 'OTHER',
                                                  name='editjustification'), nullable=True))
        if 'edit_reason' not in columns:
            batch_op.add_column(sa.Column('edit_reason', sa.String(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = [col['name'] for col in inspector.get_columns('time_records')]

    with op.batch_alter_table('time_records', schema=None) as batch_op:
        if 'edit_reason' in columns:
            batch_op.drop_column('edit_reason')
        if 'edit_justification' in columns:
            batch_op.drop_column('edit_justification')
