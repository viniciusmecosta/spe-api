from typing import Any, Generic, TypeVar
from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class MessageResponse(BaseModel):
    detail: str


class SuccessResponse(BaseModel):
    status: str = "success"
    message: str


class DataResponse(BaseModel, Generic[T]):
    status: str = "success"
    data: T


class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int
    pages: int
