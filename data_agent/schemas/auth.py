from pydantic import BaseModel


class CurrentUser(BaseModel):
    id: str
    email: str
    name: str
    tenant_id: str = ""
    permissions: list[str] = []
    token: str
    expires_at: int


class UserInfoResponse(BaseModel):
    id: str
    email: str
    name: str
    tenant_id: str
    permissions: list[str]
    expires_at: int


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    expires_in: int
    refresh_expires_in: int | None = None
    token_type: str = "Bearer"


class RefreshRequest(BaseModel):
    refresh_token: str
