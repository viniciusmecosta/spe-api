from datetime import datetime
from io import BytesIO

from PIL import Image
from sqlalchemy import select

from app.core.security import get_password_hash
from app.features.users.user_models import User
from app.shared.enums import UserRole

PASSWORD = "Synthetic-flow-password-123"
DAY = "2026-09-29"
PERIOD = {"month": 9, "year": 2026}


class ApiWorkflow:
    def __init__(self, client):
        self.client = client
        self.headers = {}
        self.calls = []

    async def request(self, method, path, expected=200, **kwargs):
        headers = kwargs.pop("headers", self.headers)
        response = await self.client.request(method, "/api/v1" + path, headers=headers, **kwargs)
        self.calls.append((method, "/api/v1" + path, response.status_code))
        assert response.status_code == expected, f"{method} {path}: {response.status_code} {response.text[:500]}"
        return response

    async def json(self, method, path, expected=200, **kwargs):
        return (await self.request(method, path, expected, **kwargs)).json()

    async def login(self, username):
        result = await self.json("POST", "/auth/login", data={"username": username, "password": PASSWORD}, headers={})
        return {"Authorization": "Bearer " + result["access_token"]}

    async def create_employee(self):
        result = await self.json("POST", "/users/", 201, json={
            "username": "qa_employee", "name": "Colaborador Alfa", "password": PASSWORD,
            "can_export_report": True, "can_manual_punch_mobile": False,
            "biometrics": [{"sensor_index": 11, "template_data": "SYNTHETIC_TEMPLATE", "finger_id": 0}],
        })
        self.employee = result
        self.employee_headers = await self.login("qa_employee")
        return result["id"]

    async def add_punch(self, user_id, kind, clock):
        return await self.json("POST", "/time-records/admin", 201, json={
            "user_id": user_id, "record_type": kind, "record_datetime": f"{DAY}T{clock}:00-03:00",
            "edit_justification": "Inclusao sintetica de teste",
        })


async def seed_root(factory):
    async with factory() as session:
        root = User(username="qa_root", name="Gestor Sintetico", role=UserRole.MAINTAINER,
                    password_hash=get_password_hash(PASSWORD))
        session.add(root)
        await session.commit()
        return (await session.scalars(select(User))).one().id


def logo_bytes():
    output = BytesIO()
    Image.new("RGB", (32, 32), "green").save(output, format="PNG")
    return output.getvalue()


def fixed_clock():
    return datetime.fromisoformat(f"{DAY}T08:00:00-03:00"), True
