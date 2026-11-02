import inspect

import pytest

from app.database.repository import AsyncBaseRepository, BaseRepository
from app.features.adjustments.adjustment_repository import AdjustmentRepository, AsyncAdjustmentRepository
from app.features.devices.device_repository import AsyncFirmwareRepository, FirmwareRepository
from app.features.payroll.payroll_repository import AsyncPayrollRepository, PayrollRepository
from app.features.time_records.time_record_repository import AsyncTimeRecordRepository, TimeRecordRepository
from app.features.users.user_repository import AsyncUserRepository, UserRepository


@pytest.mark.parametrize(('parent', 'repository', 'method', 'kwargs'), [
    (BaseRepository, AdjustmentRepository, 'create', {'obj_in': object()}),
    (AsyncBaseRepository, AsyncAdjustmentRepository, 'create', {'obj_in': object()}),
    (BaseRepository, FirmwareRepository, 'create', {'obj_in': object()}),
    (AsyncBaseRepository, AsyncFirmwareRepository, 'create', {'obj_in': object()}),
    (BaseRepository, PayrollRepository, 'create', {'obj_in': object()}),
    (AsyncBaseRepository, AsyncPayrollRepository, 'create', {'obj_in': object()}),
    (BaseRepository, TimeRecordRepository, 'create', {'obj_in': object()}),
    (AsyncBaseRepository, AsyncTimeRecordRepository, 'create', {'obj_in': object()}),
    (BaseRepository, UserRepository, 'get_multi', {'skip': 0, 'limit': 100}),
    (AsyncBaseRepository, AsyncUserRepository, 'get_multi', {'skip': 0, 'limit': 100}),
])
def test_specialized_repositories_accept_the_generic_call_contract(parent, repository, method, kwargs):
    parent_method = getattr(parent, method)
    method_override = getattr(repository, method)
    arguments = (object(), object())
    inspect.signature(parent_method).bind(*arguments, **kwargs)
    inspect.signature(method_override).bind(*arguments, **kwargs)
    parameters = inspect.signature(method_override).parameters
    for name in kwargs:
        assert parameters[name].kind != inspect.Parameter.POSITIONAL_ONLY

    parent_parameters = inspect.signature(parent_method).parameters
    extra_parameters = set(parameters) - set(parent_parameters)
    assert all(parameters[name].default is not inspect.Parameter.empty for name in extra_parameters)
