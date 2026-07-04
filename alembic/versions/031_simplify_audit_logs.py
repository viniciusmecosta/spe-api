import json

import sqlalchemy as sa
from alembic import op
from sqlalchemy.engine.reflection import Inspector

revision = '031'
down_revision = '030'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    audit_logs = conn.execute(sa.text(
        "SELECT id, user_id, actor_id, details, reason, justification, target_user_id, actor_name, target_user_name, record_type, record_time, new_data FROM audit_logs")).fetchall()

    for row in audit_logs:
        row_id = row[0]
        user_id = row[1]
        actor_id = row[2]
        details = row[3]
        reason = row[4]
        justification = row[5]
        target_user_id = row[6]
        actor_name = row[7]
        target_user_name = row[8]
        record_type = row[9]
        record_time = row[10]
        new_data_raw = row[11]

        final_user_id = user_id if user_id is not None else actor_id

        try:
            new_data = json.loads(new_data_raw) if new_data_raw else {}
        except Exception:
            new_data = {}

        legacy_data = {}
        if details: legacy_data['legacy_details'] = details
        if reason: legacy_data['legacy_reason'] = reason
        if justification: legacy_data['legacy_justification'] = justification
        if target_user_id: legacy_data['legacy_target_user_id'] = target_user_id
        if actor_name: legacy_data['legacy_actor_name'] = actor_name
        if target_user_name: legacy_data['legacy_target_user_name'] = target_user_name
        if record_type: legacy_data['legacy_record_type'] = record_type
        if record_time: legacy_data['legacy_record_time'] = str(record_time)

        if legacy_data:
            if not isinstance(new_data, dict):
                new_data = {'original_new_data': new_data}
            new_data.update(legacy_data)

        new_data_str = json.dumps(new_data) if new_data else None

        conn.execute(
            sa.text("UPDATE audit_logs SET user_id = :user_id, new_data = :new_data WHERE id = :id"),
            {"user_id": final_user_id, "new_data": new_data_str, "id": row_id}
        )

    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        batch_op.drop_constraint('fk_audit_target', type_='foreignkey')
        batch_op.drop_constraint('fk_audit_actor', type_='foreignkey')
        batch_op.drop_column('reason')
        batch_op.drop_column('justification')
        batch_op.drop_column('target_user_name')
        batch_op.drop_column('details')
        batch_op.drop_column('actor_name')
        batch_op.drop_column('record_type')
        batch_op.drop_column('actor_id')
        batch_op.drop_column('target_user_id')
        batch_op.drop_column('record_time')


def downgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = [col['name'] for col in inspector.get_columns('audit_logs')]

    with op.batch_alter_table('audit_logs', schema=None) as batch_op:
        if 'record_time' not in columns:
            batch_op.add_column(sa.Column('record_time', sa.DateTime(timezone=True), nullable=True))
        if 'target_user_id' not in columns:
            batch_op.add_column(sa.Column('target_user_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key('fk_audit_target', 'users', ['target_user_id'], ['id'])
        if 'actor_id' not in columns:
            batch_op.add_column(sa.Column('actor_id', sa.Integer(), nullable=True))
            batch_op.create_foreign_key('fk_audit_actor', 'users', ['actor_id'], ['id'])
        if 'record_type' not in columns:
            batch_op.add_column(sa.Column('record_type', sa.String(), nullable=True))
        if 'actor_name' not in columns:
            batch_op.add_column(sa.Column('actor_name', sa.String(), nullable=True))
        if 'details' not in columns:
            batch_op.add_column(sa.Column('details', sa.String(), nullable=True))
        if 'target_user_name' not in columns:
            batch_op.add_column(sa.Column('target_user_name', sa.String(), nullable=True))
        if 'justification' not in columns:
            batch_op.add_column(sa.Column('justification', sa.String(), nullable=True))
        if 'reason' not in columns:
            batch_op.add_column(sa.Column('reason', sa.String(), nullable=True))
