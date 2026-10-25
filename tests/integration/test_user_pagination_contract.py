from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import DomainException
from app.features.users.user_models import User
from app.features.users.user_repository import AsyncUserRepository

pytestmark = pytest.mark.asyncio


async def test_user_cursor_preserves_every_order_with_duplicate_and_null_sort_values(pg_session_factory):
    names = ['Bia', 'Ana', None, 'Caio', 'Ana', None]
    usernames = ['c-user', 'b-user', 'a-user', 'd-user', 'f-user', 'e-user']
    initial = datetime(2026, 10, 1, tzinfo=UTC)
    async with pg_session_factory() as session:
        users = [User(username=username, name=name, created_at=initial + timedelta(days=index % 3),
                      updated_at=initial + timedelta(days=index % 2))
                 for index, (name, username) in enumerate(zip(names, usernames, strict=True))]
        session.add_all(users)
        await session.commit()
        ids = [user.id for user in users]
        expected_names = {
            'asc': [ids[index] for index in [1, 4, 0, 3, 2, 5]],
            'desc': [ids[index] for index in [5, 2, 3, 0, 4, 1]],
        }
        repo = AsyncUserRepository()
        for order_by in ['id', 'name', 'username', 'created_at', 'updated_at']:
            for direction in ['asc', 'desc']:
                complete = await repo.get_multi(session, order_by=order_by, order_direction=direction)
                expected = [user.id for user in complete]
                if order_by == 'name':
                    assert expected == expected_names[direction]
                if order_by == 'id':
                    assert expected == (ids if direction == 'asc' else ids[::-1])
                cursor = 0
                collected = []
                for _ in range(len(users) + 1):
                    page = await repo.get_multi(session, after_id=cursor, limit=2,
                                                order_by=order_by, order_direction=direction)
                    if not page:
                        break
                    collected.extend(user.id for user in page)
                    cursor = page[-1].id
                assert collected == expected, (order_by, direction, collected, expected)
                assert len(set(collected)) == len(users)
        filtered = await repo.get_multi(session, after_id=ids[1], order_by='name', search='Ana')
        assert [user.id for user in filtered] == [ids[4]]
        offset = await repo.get_multi(session, skip=2, limit=2)
        assert [user.id for user in offset] == ids[2:4]
        missing_id = max(ids) + 1
        with pytest.raises(DomainException) as caught:
            await repo.get_multi(session, after_id=missing_id)
        assert caught.value.status_code == 422
