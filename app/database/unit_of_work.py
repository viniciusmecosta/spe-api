from contextlib import asynccontextmanager
from functools import wraps
from inspect import isawaitable, signature


async def _invoke(operation):
    result = operation()
    if isawaitable(result):
        await result


def persist_sync_changes(session):
    if session.info.get('unit_of_work_depth', 0):
        session.flush()
    else:
        session.commit()


async def persist_changes(session):
    if session.info.get('unit_of_work_depth', 0):
        await _invoke(session.flush)
    else:
        await _invoke(session.commit)


@asynccontextmanager
async def unit_of_work(session):
    depth = session.info.get('unit_of_work_depth', 0)
    session.info['unit_of_work_depth'] = depth + 1
    try:
        yield session
        if depth == 0:
            await _invoke(session.commit)
    except BaseException:
        if depth == 0:
            await _invoke(session.rollback)
        raise
    finally:
        if depth:
            session.info['unit_of_work_depth'] = depth
        else:
            session.info.pop('unit_of_work_depth', None)


def transactional(method=None, *, response_model=None):
    if method is None:
        return lambda wrapped: transactional(wrapped, response_model=response_model)
    parameters = signature(method)

    @wraps(method)
    async def execute(self, *args, **kwargs):
        arguments = parameters.bind(self, *args, **kwargs).arguments
        session = arguments.get('db') or self.db
        async with unit_of_work(session):
            result = await method(self, *args, **kwargs)
            if response_model is not None:
                result = response_model.model_validate(result)
                result.model_dump(mode='json')
            return result

    return execute
