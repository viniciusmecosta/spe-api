from typing import Sequence, Union

from alembic import op

revision: str = '030'
down_revision: Union[str, None] = '029'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # time_records
    op.create_index('idx_tr_user_date', 'time_records', ['user_id', 'record_datetime'])
    op.create_index('idx_tr_ignored', 'time_records', ['is_ignored'])

    # adjustment_requests
    op.create_index('idx_adj_user_date', 'adjustment_requests', ['user_id', 'target_date'])
    op.create_index('idx_adj_status', 'adjustment_requests', ['status'])

    # audit_logs
    op.create_index('idx_audit_user_action', 'audit_logs', ['user_id', 'action'])
    op.create_index('idx_audit_entity_time', 'audit_logs', ['entity', 'entity_id', 'timestamp'])


def downgrade() -> None:
    op.drop_index('idx_tr_user_date', table_name='time_records')
    op.drop_index('idx_tr_ignored', table_name='time_records')
    op.drop_index('idx_adj_user_date', table_name='adjustment_requests')
    op.drop_index('idx_adj_status', table_name='adjustment_requests')
    op.drop_index('idx_audit_user_action', table_name='audit_logs')
    op.drop_index('idx_audit_entity_time', table_name='audit_logs')
