from pydantic import BaseModel, Field

from app.features.users.user_schemas import PasswordInput


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 0
    refresh_token: str | None = None
    refresh_expires_in: int | None = None
    password_change_required: bool = False


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=40, max_length=256)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: PasswordInput


class TokenPayload(BaseModel):
    sub: int | None = None
    ver: int = 0
    name: str | None = None
    role: str | None = None
    purpose: str = "access"
    sid: str | None = None
