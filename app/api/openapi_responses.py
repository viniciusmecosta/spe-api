from typing import Any

UNAUTHORIZED_RESPONSE: dict[int | str, dict[str, Any]] = {
    401: {"description": "Não autenticado"},
}

FORBIDDEN_RESPONSE: dict[int | str, dict[str, Any]] = {
    403: {"description": "Permissão insuficiente"},
}

NOT_FOUND_RESPONSE: dict[int | str, dict[str, Any]] = {
    404: {"description": "Recurso não encontrado"},
}

BAD_REQUEST_RESPONSE: dict[int | str, dict[str, Any]] = {
    400: {"description": "Requisição inválida ou regras de negócio violadas"},
}

AUTH_RESPONSES: dict[int | str, dict[str, Any]] = {
    **UNAUTHORIZED_RESPONSE,
    **FORBIDDEN_RESPONSE,
}

CRUD_RESPONSES: dict[int | str, dict[str, Any]] = {
    **UNAUTHORIZED_RESPONSE,
    **FORBIDDEN_RESPONSE,
    **NOT_FOUND_RESPONSE,
}
