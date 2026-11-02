import sqlalchemy as sa

from alembic import op

revision = '026'
down_revision = '025'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('companies', sa.Column('logo_path', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('companies', 'logo_path')
