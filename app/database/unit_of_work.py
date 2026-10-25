from contextlib import asynccontextmanager
from functools import wraps
from inspect import signature


async def persist_changes(session):
    if session.info.get('unit_of_work_depth', 0):
        await session.flush()
    else:
        await session.commit()


@asynccontextmanager
async def unit_of_work(session):
    depth = session.info.get('unit_of_work_depth', 0)
    session.info['unit_of_work_depth'] = depth + 1
    try:
        yield session
        if depth == 0:
            await session.commit()
    except BaseException:
        if depth == 0:
            await session.rollback()
        raise
    finally:
        if depth:
            session.info['unit_of_work_depth'] = depth
        else:
            session.info.pop('unit_of_work_depth', None)


def transactional(method):
    parameters = signature(method)

    @wraps(method)
    async def execute(self, *args, **kwargs):
        arguments = parameters.bind(self, *args, **kwargs).arguments
        session = arguments.get('db') or self.db
        async with unit_of_work(session):
            return await method(self, *args, **kwargs)

    return execute
