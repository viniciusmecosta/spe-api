from unittest.mock import MagicMock
import pytest
from app.features.users.user_repository import user_repository, UserRepository
from app.features.users.user_models import User
from app.features.users.user_schemas import UserUpdate
from app.features.devices.device_models import UserBiometric
from app.shared.enums import UserRole


def test_user_repository_methods(db_session, normal_user):
    repo = UserRepository()

    u = repo.get_by_username(db_session, normal_user.username)
    assert u.id == normal_user.id

    u2 = repo.get(db_session, normal_user.id)
    assert u2.id == normal_user.id

    users = repo.get_multi(
        db_session,
        is_active=True,
        role=normal_user.role,
        search=normal_user.username[:3],
        order_by="name",
        order_direction="asc"
    )
    assert len(users) >= 1

    up = UserUpdate(name="New Name Pydantic", password="newpassword123")
    updated = repo.update(db_session, normal_user, up)
    assert updated.name == "New Name Pydantic"

    class BioObj:
        def __init__(self, id, sensor_index, template_data, finger_id):
            self.id = id
            self.sensor_index = sensor_index
            self.template_data = template_data
            self.finger_id = finger_id

    bio_obj = BioObj(id=None, sensor_index=999, template_data="data", finger_id=1)
    repo.update(db_session, normal_user, {"biometrics": [bio_obj]})
    assert len(normal_user.biometrics) == 1

    bio_id = normal_user.biometrics[0].id
    bio_obj_update = BioObj(id=bio_id, sensor_index=999, template_data="new_data", finger_id=2)
    repo.update(db_session, normal_user, {"biometrics": [bio_obj_update]})
    assert normal_user.biometrics[0].finger_id == 2

    other_user = User(username="other_user_repo_test", name="Other", role=UserRole.EMPLOYEE, password_hash="hash")
    db_session.add(other_user)
    db_session.commit()
    db_session.refresh(other_user)

    db_session.add(UserBiometric(user_id=other_user.id, sensor_index=888, template_data="data"))
    db_session.commit()

    with pytest.raises(ValueError, match="duplicado na mesma requisicao"):
        repo.update(db_session, normal_user, {"biometrics": [
            {"id": None, "sensor_index": 777, "template_data": "d1", "finger_id": 1},
            {"id": None, "sensor_index": 777, "template_data": "d2", "finger_id": 2}
        ]})

    with pytest.raises(ValueError, match="Index ja cadastrada"):
        repo.update(db_session, normal_user, {"biometrics": [{"id": None, "sensor_index": 888, "template_data": "d", "finger_id": 1}]})

    users_desc = repo.get_multi(
        db_session,
        order_by="name",
        order_direction="desc"
    )
    assert len(users_desc) >= 1

    active_emps = repo.get_active_employees(db_session)
    assert isinstance(active_emps, list)
