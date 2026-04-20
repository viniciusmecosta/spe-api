import sqlalchemy as sa
from alembic import op

revision = '018'
down_revision = '017'
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column('users', sa.Column('is_exempt_from_rules', sa.Boolean(), server_default=sa.false(), nullable=False))

def downgrade() -> None:
    op.drop_column('users', 'is_exempt_from_rules')