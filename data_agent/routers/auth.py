import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse

from common.config import SETTINGS
from data_agent.dependencies import get_auth_service, get_current_user
from data_agent.schemas import CurrentUser, RefreshRequest, TokenResponse, UserInfoResponse
from data_agent.services import AuthError, AuthService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _redirect_uri(request: Request) -> str:
    return SETTINGS.auth.redirect_uri or str(request.url_for("auth_callback"))


@router.get("/login")
async def login(
        request: Request,
        auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    """Redirects the browser to the Fabrix Keycloak sign-in page (same one 'fadk login' opens)."""
    return RedirectResponse(auth_service.build_login_url(_redirect_uri(request)))


@router.get("/callback", response_model=TokenResponse, name="auth_callback")
async def callback(
        request: Request,
        auth_service: Annotated[AuthService, Depends(get_auth_service)],
        code: Annotated[str | None, Query()] = None,
        state: Annotated[str | None, Query()] = None,
        error: Annotated[str | None, Query()] = None,
):
    """Keycloak redirects here after sign-in; exchanges the one-time code for tokens."""
    if error is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Sign-in failed: {error}")
    if code is None or state is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing code or state.")

    try:
        tokens = await auth_service.exchange_code(code, state, _redirect_uri(request))
    except AuthError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    return TokenResponse(**tokens)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
        request: RefreshRequest,
        auth_service: Annotated[AuthService, Depends(get_auth_service)],
):
    """Exchanges a refresh token for a new access token (silent renewal, no browser)."""
    try:
        tokens = await auth_service.refresh_tokens(request.refresh_token)
    except AuthError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    return TokenResponse(**tokens)


@router.get("/me", response_model=UserInfoResponse)
async def me(current_user: Annotated[CurrentUser, Depends(get_current_user)]):
    """Returns the identity behind the presented token; 401 if missing/expired."""
    return UserInfoResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        tenant_id=current_user.tenant_id,
        permissions=current_user.permissions,
        expires_at=current_user.expires_at,
    )
