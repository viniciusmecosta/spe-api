from alembic import op


revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("LOCK TABLE audit_logs IN ACCESS EXCLUSIVE MODE")
    op.execute("DELETE FROM audit_logs WHERE action = 'LOGIN'")
    op.execute("""
        WITH ranked AS (
            SELECT id, ROW_NUMBER() OVER (ORDER BY id) AS new_id
            FROM audit_logs
        )
        UPDATE audit_logs AS target
        SET id = -ranked.new_id
        FROM ranked
        WHERE target.id = ranked.id
    """)
    op.execute("UPDATE audit_logs SET id = -id")
    op.execute("""
        SELECT setval(
            pg_get_serial_sequence('audit_logs', 'id')::regclass,
            GREATEST(COALESCE((SELECT MAX(id) FROM audit_logs), 0), 1),
            EXISTS (SELECT 1 FROM audit_logs)
        )
    """)


def downgrade() -> None:
    raise NotImplementedError("A remoção das auditorias de login não pode ser revertida")
