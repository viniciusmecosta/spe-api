from alembic import op

revision = '041'
down_revision = '040'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("UPDATE audit_logs SET action = 'DELETE_ADJUSTMENT' WHERE action = 'SOFT_DELETE_ADJUSTMENT'")


def downgrade():
    op.execute("UPDATE audit_logs SET action = 'SOFT_DELETE_ADJUSTMENT' WHERE action = 'DELETE_ADJUSTMENT'")
