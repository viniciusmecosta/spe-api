import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

from alembic import op

revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None

_ENUM_NAME = 'editjustification'
_ENUM_VALUES = ('FORGOT_ENTRY', 'FORGOT_EXIT', 'SYSTEM_ERROR', 'INITIAL_INCLUSION',
                'INITIAL_EDIT', 'REGISTRATION_MISTAKE', 'IRRELEVANT_RECORD', 'OTHER')


def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = [col['name'] for col in inspector.get_columns('time_records')]

    if 'edit_justification' not in columns:
        enum_type = sa.Enum(*_ENUM_VALUES, name=_ENUM_NAME)
        enum_type.create(conn, checkfirst=True)
        op.add_column('time_records', sa.Column('edit_justification', enum_type, nullable=True))

    if 'edit_reason' not in columns:
        op.add_column('time_records', sa.Column('edit_reason', sa.String(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = [col['name'] for col in inspector.get_columns('time_records')]

    if 'edit_reason' in columns:
        op.drop_column('time_records', 'edit_reason')
    if 'edit_justification' in columns:
        op.drop_column('time_records', 'edit_justification')
        sa.Enum(name=_ENUM_NAME).drop(conn, checkfirst=True)
