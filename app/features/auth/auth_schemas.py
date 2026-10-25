from pydantic import BaseModel


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenPayload(BaseModel):
    sub: int | None = None
    ver: int = 0
    name: str | None = None
    role: str | None = None
