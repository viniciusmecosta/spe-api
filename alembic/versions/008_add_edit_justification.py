import sqlalchemy as sa
from alembic import op

revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('time_records', sa.Column('edit_justification', sa.Enum('FORGOT_ENTRY', 'FORGOT_EXIT', 'SYSTEM_ERROR', 'OTHER', name='editjustification'), nullable=True))

def downgrade() -> None:
    with op.batch_alter_table('time_records') as batch_op:
        batch_op.drop_column('edit_justification')