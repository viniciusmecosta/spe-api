from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import (
    _get_error_title,
    _get_error_type,
    _translate_pydantic_msg,
    setup_exception_handlers,
)


def test_translate_pydantic_msg():
    assert _translate_pydantic_msg("field required") == "Campo obrigatório"
    assert _translate_pydantic_msg("value is not a valid email address") == "E-mail inválido"
    assert _translate_pydantic_msg("ensure this value has at least") == "O tamanho mínimo não foi atingido"
    assert _translate_pydantic_msg("ensure this value has at most") == "O tamanho máximo foi excedido"
    assert _translate_pydantic_msg("Input should be a valid string") == "Deve ser um texto válido"
    assert _translate_pydantic_msg("Input should be a valid integer") == "Deve ser um número inteiro"
    assert _translate_pydantic_msg("Input should be greater than") == "O valor deve ser maior"
    assert _translate_pydantic_msg("Input should be less than") == "O valor deve ser menor"
    assert _translate_pydantic_msg("String should have at least") == "O texto deve ter pelo menos"
    assert _translate_pydantic_msg("String should have at most") == "O texto deve ter no máximo"
    assert _translate_pydantic_msg("Unknown error message") == "Unknown error message"


def test_get_error_type():
    assert _get_error_type(400, "custom-slug") == "https://api.spe.com/erros/custom-slug"
    assert _get_error_type(418) == "https://api.spe.com/erros/http-error-418"


def test_get_error_title():
    title_418 = _get_error_title(418)
    assert isinstance(title_418, str) and len(title_418) > 0
    assert _get_error_title(999) == "Erro"


def test_setup_exception_handlers():
    test_app = FastAPI()
    setup_exception_handlers(test_app)

    @test_app.get("/error-500")
    def raise_500():
        raise StarletteHTTPException(status_code=500, detail="Internal Error")

    @test_app.get("/error-dict")
    def raise_dict():
        raise StarletteHTTPException(status_code=400, detail={"msg": "bad request"})

    @test_app.get("/error-404")
    def raise_404():
        raise StarletteHTTPException(status_code=404, detail="Not Found")

    @test_app.get("/error-401-user")
    def raise_401_user():
        raise StarletteHTTPException(status_code=401, detail="Incorrect username or password")

    @test_app.get("/error-401-cred")
    def raise_401_cred():
        raise StarletteHTTPException(status_code=401, detail="Could not validate credentials")

    @test_app.get("/error-sqlalchemy")
    def raise_db_err():
        raise SQLAlchemyError("Database explosion")

    @test_app.get("/error-general")
    def raise_general():
        raise RuntimeError("General exception")

    @test_app.get("/uploads/file.pdf")
    def raise_upload_404():
        raise StarletteHTTPException(status_code=404, detail="Not Found")

    from pydantic import BaseModel
    class ValidationItem(BaseModel):
        num: int

    @test_app.post("/test-validation")
    def test_val(item: ValidationItem):
        return item

    from app.core.exceptions import DomainException
    @test_app.get("/error-domain")
    def raise_domain():
        raise DomainException(detail="Erro de dominio customizado", status_code=400)

    client = TestClient(test_app, raise_server_exceptions=False)

    res = client.get("/error-domain")
    assert res.status_code == 400
    assert res.json()["detail"] == "Erro de dominio customizado"

    res = client.get("/uploads/file.pdf")
    assert res.status_code == 404
    assert "documento ou arquivo solicitado" in res.json()["detail"]

    res = client.post("/test-validation", json={"num": "abc"})
    assert res.status_code == 422
    assert "invalid_params" in res.json()

    res = client.get("/error-500")
    assert res.status_code == 500

    res = client.get("/error-dict")
    assert res.status_code == 400

    res = client.get("/error-404")
    assert res.status_code == 404
    assert "A URL acessada não existe" in res.json()["detail"]

    res = client.get("/error-401-user")
    assert res.status_code == 401
    assert res.json()["detail"] == "Usuário ou senha incorretos."

    res = client.get("/error-401-cred")
    assert res.status_code == 401
    assert res.json()["detail"] == "Não foi possível validar as credenciais de acesso."

    res = client.get("/error-sqlalchemy")
    assert res.status_code == 500
    assert res.json()["title"] == "Erro no Banco de Dados"

    res = client.get("/error-general")
    assert res.status_code == 500
    assert res.json()["detail"] == "Um erro inesperado ocorreu no servidor."
