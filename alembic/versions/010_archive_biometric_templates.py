import sqlalchemy as sa

from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column("user_biometrics", "template_data")


def downgrade():
    op.add_column("user_biometrics", sa.Column("template_data", sa.Text(), nullable=True))
