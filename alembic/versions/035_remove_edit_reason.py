import sqlalchemy as sa
from alembic import op

revision = '035'
down_revision = '034'
branch_labels = None
depends_on = None

def upgrade() -> None:
    with op.batch_alter_table('time_records', schema=None) as batch_op:
        batch_op.drop_column('edit_reason')
        batch_op.alter_column('edit_justification',
                              existing_type=sa.VARCHAR(length=20),
                              type_=sa.String(length=70),
                              existing_nullable=True)

def downgrade() -> None:
    with op.batch_alter_table('time_records', schema=None) as batch_op:
        batch_op.add_column(sa.Column('edit_reason', sa.String(), nullable=True))
        batch_op.alter_column('edit_justification',
                              existing_type=sa.String(length=70),
                              type_=sa.Enum('FORGOT_ENTRY', 'FORGOT_EXIT', 'SYSTEM_ERROR', 'INITIAL_INCLUSION', 'INITIAL_EDIT', 'REGISTRATION_MISTAKE', 'IRRELEVANT_RECORD', 'OTHER', name='editjustification'),
                              existing_nullable=True)