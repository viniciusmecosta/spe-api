import sqlalchemy as sa

from alembic import op

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "biometric_template_archive",
        sa.Column(
            "biometric_id",
            sa.Integer(),
            sa.ForeignKey("user_biometrics.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("template_data", sa.Text(), nullable=False),
    )
    op.execute(
        "INSERT INTO biometric_template_archive (biometric_id, template_data) "
        "SELECT id, template_data FROM user_biometrics WHERE template_data IS NOT NULL"
    )
    op.drop_column("user_biometrics", "template_data")


def downgrade():
    op.add_column("user_biometrics", sa.Column("template_data", sa.Text(), nullable=True))
    op.execute(
        "UPDATE user_biometrics SET template_data = "
        "(SELECT template_data FROM biometric_template_archive "
        "WHERE biometric_id = user_biometrics.id)"
    )
    op.drop_table("biometric_template_archive")
