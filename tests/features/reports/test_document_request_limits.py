from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.middleware import body_limit
from app.middleware.body_limit import PathBodyLimitMiddleware


def test_only_verification_endpoint_receives_larger_request_limit(monkeypatch):
    monkeypatch.setattr(body_limit, "DOCUMENT_VERIFICATION_REQUEST_LIMIT", 128)
    app = FastAPI()
    app.add_middleware(PathBodyLimitMiddleware, max_body_size=32)

    @app.post("/api/v1/documents/verify")
    @app.post("/other")
    async def endpoint(request: Request):
        return {"size": len(await request.body())}

    with TestClient(app) as client:
        assert client.post("/api/v1/documents/verify", content=b"x" * 64).status_code == 200
        assert client.post("/api/v1/documents/verify", content=b"x" * 129).status_code == 413
        assert client.post("/other", content=b"x" * 33).status_code == 413
