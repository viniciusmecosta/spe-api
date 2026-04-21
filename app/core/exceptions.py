import http
import logging
from typing import Optional

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


def _translate_pydantic_msg(msg: str) -> str:
    translations = {
        "field required": "Campo obrigatório",
        "value is not a valid email address": "E-mail inválido",
        "ensure this value has at least": "O tamanho mínimo não foi atingido",
        "ensure this value has at most": "O tamanho máximo foi excedido",
        "Input should be a valid string": "Deve ser um texto válido",
        "Input should be a valid integer": "Deve ser um número inteiro",
        "Input should be greater than": "O valor deve ser maior",
        "Input should be less than": "O valor deve ser menor",
        "String should have at least": "O texto deve ter pelo menos",
        "String should have at most": "O texto deve ter no máximo"
    }
    for eng_key, pt_val in translations.items():
        if eng_key in msg:
            return pt_val
    return msg

def _get_error_type(status_code: int, custom_slug: Optional[str] = None) -> str:
    base_url = "https://api.spe.com/erros/"
    if custom_slug:
        return f"{base_url}{custom_slug}"
    slug_map = {
        400: "requisicao-invalida",
        401: "nao-autorizado",
        403: "acesso-negado",
        404: "recurso-nao-encontrado",
        409: "conflito",
        422: "erro-de-validacao",
        500: "erro-interno-servidor"
    }
    slug = slug_map.get(status_code, f"http-error-{status_code}")
    return f"{base_url}{slug}"

def _get_error_title(status_code: int) -> str:
    titles_pt = {
        400: "Requisição Inválida",
        401: "Não Autorizado",
        403: "Acesso Negado",
        404: "Recurso Não Encontrado",
        409: "Conflito",
        422: "Erro de Validação",
        500: "Erro Interno do Servidor"
    }
    if status_code in titles_pt:
        return titles_pt[status_code]
    try:
        return http.HTTPStatus(status_code).phrase
    except ValueError:
        return "Erro"

def setup_exception_handlers(app: FastAPI):
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        if exc.status_code >= 500:
            logger.error(f"HTTP {exc.status_code} na rota {request.url.path}: {exc.detail}", exc_info=True)
        else:
            logger.warning(f"HTTP {exc.status_code} na rota {request.url.path}: {exc.detail}")

        detail_msg = exc.detail
        if isinstance(detail_msg, dict):
            detail_msg = str(detail_msg)

        if exc.status_code == status.HTTP_404_NOT_FOUND and detail_msg == "Not Found":
            detail_msg = "A URL acessada não existe. Verifique a documentação em /docs para ver as rotas disponíveis."
        elif exc.status_code == status.HTTP_401_UNAUTHORIZED and detail_msg == "Incorrect username or password":
            detail_msg = "Usuário ou senha incorretos."
        elif exc.status_code == status.HTTP_401_UNAUTHORIZED and detail_msg == "Could not validate credentials":
            detail_msg = "Não foi possível validar as credenciais de acesso."

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "type": _get_error_type(exc.status_code),
                "title": _get_error_title(exc.status_code),
                "status": exc.status_code,
                "detail": detail_msg,
                "instance": request.url.path
            }
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        logger.warning(f"Erro de validação em {request.method} {request.url.path}: {exc.errors()}")
        invalid_params = [
            {
                "loc": " -> ".join(map(str, err.get("loc", []))),
                "msg": _translate_pydantic_msg(err.get("msg", "")),
                "type": err.get("type")
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "type": _get_error_type(status.HTTP_422_UNPROCESSABLE_ENTITY),
                "title": _get_error_title(status.HTTP_422_UNPROCESSABLE_ENTITY),
                "status": status.HTTP_422_UNPROCESSABLE_ENTITY,
                "detail": "Os dados fornecidos na requisição são inválidos ou estão incompletos.",
                "instance": request.url.path,
                "invalid_params": invalid_params
            }
        )

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError):
        logger.error(f"Database error em {request.url.path}: {str(exc)}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "type": _get_error_type(status.HTTP_500_INTERNAL_SERVER_ERROR, "erro-banco-de-dados"),
                "title": "Erro no Banco de Dados",
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "detail": "Ocorreu um erro interno ao processar a operação no banco de dados.",
                "instance": request.url.path
            }
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unexpected error em {request.url.path}: {str(exc)}", exc_info=True)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "type": _get_error_type(status.HTTP_500_INTERNAL_SERVER_ERROR),
                "title": _get_error_title(status.HTTP_500_INTERNAL_SERVER_ERROR),
                "status": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "detail": "Um erro inesperado ocorreu no servidor.",
                "instance": request.url.path
            }
        )