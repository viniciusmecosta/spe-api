from unittest.mock import MagicMock

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from app.core.security import create_access_token
from app.middleware.request_logging import RequestLoggingMiddleware, _extract_user_name


def test_extract_user_name():
    token = create_access_token(subject="1", name="João da Silva")
    req = MagicMock(spec=Request)
    req.headers.get.side_effect = lambda k, d="": f"Bearer {token}" if k.lower() == "authorization" else d
    assert _extract_user_name(req) == "João Silva"

    req2 = MagicMock(spec=Request)
    req2.headers.get.side_effect = lambda k, d="": "Bearer invalid" if k.lower() == "authorization" else d
    req2.state.attempted_user = "Maria Souza"
    assert _extract_user_name(req2) == "Maria Souza"


def test_middleware_status_codes():
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/ok")
    def ok_route(request: Request):
        request.state.device_name = "Device1"
        return {"ok": True}

    @app.get("/warn")
    def warn_route(request: Request):
        request.state.ntp_error = True
        return JSONResponse(status_code=400, content={"error": "bad"})

    @app.get("/err")
    def err_route():
        return JSONResponse(status_code=500, content={"error": "server"})

    client = TestClient(app)
    assert client.get("/ok").status_code == 200
    assert client.get("/warn").status_code == 400
    assert client.get("/err").status_code == 500
