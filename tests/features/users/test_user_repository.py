from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

import pytest
import pytest_asyncio
from app.database.base import Base
from app.features.devices.device_models import UserBiometric
from app.features.users.user_models import User
from app.features.users.user_repository import AsyncUserRepository
from app.features.users.user_schemas import UserUpdate
from app.shared.enums import UserRole


@pytest_asyncio.fixture
async def async_db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SessionClass = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionClass() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def async_normal_user(async_db_session):
    usr = User(
        username="testuser",
        name="Test User",
        password_hash="hashedpass",
        role=UserRole.EMPLOYEE,
        is_active=True
    )
    async_db_session.add(usr)
    await async_db_session.commit()
    await async_db_session.refresh(usr, attribute_names=["biometrics"])
    return usr


@pytest.mark.asyncio
async def test_user_repository_methods(async_db_session, async_normal_user):
    repo = AsyncUserRepository()

    u = await repo.get_by_username(async_db_session, async_normal_user.username)
    assert u.id == async_normal_user.id

    u2 = await repo.get(async_db_session, async_normal_user.id)
    assert u2.id == async_normal_user.id

    users = await repo.get_multi(
        async_db_session,
        is_active=True,
        role=async_normal_user.role,
        search=async_normal_user.username[:3],
        order_by="name",
        order_direction="asc"
    )
    assert len(users) >= 1

    up = UserUpdate(name="New Name Pydantic", password="newpassword123")
    updated = await repo.update(async_db_session, db_obj=async_normal_user, obj_in=up)
    assert updated.name == "New Name Pydantic"

    class BioObj:
        def __init__(self, id, sensor_index, template_data, finger_id):
            self.id = id
            self.sensor_index = sensor_index
            self.template_data = template_data
            self.finger_id = finger_id

    bio_obj = BioObj(id=None, sensor_index=999, template_data="data", finger_id=1)
    await repo.update(async_db_session, db_obj=async_normal_user, obj_in={"biometrics": [bio_obj]})
    await async_db_session.refresh(async_normal_user, attribute_names=['biometrics'])
    assert len(async_normal_user.biometrics) == 1

    bio_id = async_normal_user.biometrics[0].id
    bio_obj_update = BioObj(id=bio_id, sensor_index=999, template_data="new_data", finger_id=2)
    await repo.update(async_db_session, db_obj=async_normal_user, obj_in={"biometrics": [bio_obj_update]})
    await async_db_session.refresh(async_normal_user, attribute_names=['biometrics'])
    assert async_normal_user.biometrics[0].finger_id == 2

    other_user = User(username="other_user_repo_test", name="Other", role=UserRole.EMPLOYEE, password_hash="hash")
    async_db_session.add(other_user)
    await async_db_session.commit()
    await async_db_session.refresh(other_user)

    async_db_session.add(UserBiometric(user_id=other_user.id, sensor_index=888, template_data="data"))
    await async_db_session.commit()

    with pytest.raises(ValueError, match="duplicado na mesma requisicao"):
        await repo.update(async_db_session, db_obj=async_normal_user, obj_in={"biometrics": [
            {"id": None, "sensor_index": 777, "template_data": "d1", "finger_id": 1},
            {"id": None, "sensor_index": 777, "template_data": "d2", "finger_id": 2}
        ]})

    with pytest.raises(ValueError, match="Index ja cadastrada"):
        await repo.update(async_db_session, db_obj=async_normal_user,
                          obj_in={
                              "biometrics": [{"id": None, "sensor_index": 888, "template_data": "d", "finger_id": 1}]})

    users_desc = await repo.get_multi(
        async_db_session,
        order_by="name",
        order_direction="desc"
    )
    assert len(users_desc) >= 1

    active_emps = await repo.get_active_employees(async_db_session)
    assert isinstance(active_emps, list)
