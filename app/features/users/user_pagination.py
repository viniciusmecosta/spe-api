from sqlalchemy import and_, or_

from app.features.users.user_models import User


def user_order_column(order_by: str):
    columns = {
        'id': User.id,
        'name': User.name,
        'username': User.username,
        'created_at': User.created_at,
        'updated_at': User.updated_at,
    }
    return columns.get(order_by, User.id)


def user_sort_order(column, descending: bool):
    if descending:
        return column.desc().nullsfirst(), User.id.desc()
    return column.asc().nullslast(), User.id.asc()


def user_cursor_condition(column, after_id: int, cursor_value, descending: bool):
    id_after = User.id < after_id if descending else User.id > after_id
    if cursor_value is None:
        remaining_nulls = and_(column.is_(None), id_after)
        if descending:
            return or_(column.is_not(None), remaining_nulls)
        return remaining_nulls
    values_after = column < cursor_value if descending else column > cursor_value
    condition = or_(values_after, and_(column == cursor_value, id_after))
    if not descending:
        condition = or_(condition, column.is_(None))
    return condition
