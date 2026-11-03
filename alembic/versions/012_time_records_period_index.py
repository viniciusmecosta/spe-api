from alembic import op

revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.create_index(
            "idx_tr_date_id", "time_records", ["record_datetime", "id"], postgresql_concurrently=True,
        )


def downgrade():
    with op.get_context().autocommit_block():
        op.drop_index("idx_tr_date_id", table_name="time_records", postgresql_concurrently=True)
