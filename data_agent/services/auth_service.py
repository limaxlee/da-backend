import base64
import contextvars
import hashlib
import logging
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from jwt import PyJWKClient, InvalidTokenError

from common.config import SETTINGS
from data_agent.schemas import CurrentUser

logger = logging.getLogger(__name__)

# Token of the user currently being served; the model layer reads this to call
# the Fabrix model API on behalf of that user instead of a server-wide account.
current_fabrix_token: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_fabrix_token", default=None
)

_STATE_TTL_SECONDS = 600


class AuthError(Exception):
    pass


class AuthService:
    """Verifies Fabrix Keycloak access tokens and drives the OIDC PKCE login flow.

    Verification is local: Keycloak's public keys (JWKS) are fetched once and
    cached by PyJWKClient, so no network call is made per request.
    """

    def __init__(self) -> None:
        issuer = SETTINGS.auth.issuer.rstrip("/")
        self._issuer = issuer
        self._client_id = SETTINGS.auth.client_id
        self._auth_endpoint = f"{issuer}/protocol/openid-connect/auth"
        self._token_endpoint = f"{issuer}/protocol/openid-connect/token"
        self._jwks = PyJWKClient(f"{issuer}/protocol/openid-connect/certs", cache_keys=True)
        # state -> (code_verifier, created_at); single-instance in-memory store
        self._pending_logins: dict[str, tuple[str, float]] = {}

    def verify_token(self, token: str) -> dict[str, Any]:
        try:
            signing_key = self._jwks.get_signing_key_from_jwt(token)
            return jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                issuer=self._issuer,
                leeway=30,
                # Keycloak sets aud per client; the platform accepts any client
                # of the fabrix realm (fadk CLI, frontend, this backend).
                options={"verify_aud": False},
            )
        except InvalidTokenError as error:
            raise AuthError(f"Invalid or expired token: {error}") from error

    def user_from_token(self, token: str) -> CurrentUser:
        claims = self.verify_token(token)
        return CurrentUser(
            id=claims["sub"],
            email=claims.get("user_email") or claims.get("email") or claims.get("preferred_username", ""),
            name=claims.get("en_name") or claims.get("name", ""),
            tenant_id=claims.get("tenant_id", ""),
            permissions=claims.get("permission", []),
            token=token,
            expires_at=claims["exp"],
        )

    def build_login_url(self, redirect_uri: str) -> str:
        code_verifier = secrets.token_urlsafe(48)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode("ascii")).digest()
        ).rstrip(b"=").decode("ascii")
        state = secrets.token_urlsafe(24)

        self._evict_stale_logins()
        self._pending_logins[state] = (code_verifier, time.monotonic())

        query = urlencode({
            "response_type": "code",
            "client_id": self._client_id,
            "redirect_uri": redirect_uri,
            "scope": "openid profile email",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        })
        return f"{self._auth_endpoint}?{query}"

    async def exchange_code(self, code: str, state: str, redirect_uri: str) -> dict[str, Any]:
        pending = self._pending_logins.pop(state, None)
        if pending is None:
            raise AuthError("Unknown or expired login state. Start the login again.")

        code_verifier, created_at = pending
        if time.monotonic() - created_at > _STATE_TTL_SECONDS:
            raise AuthError("Login attempt expired. Start the login again.")

        return await self._request_tokens({
            "grant_type": "authorization_code",
            "client_id": self._client_id,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier,
        })

    async def refresh_tokens(self, refresh_token: str) -> dict[str, Any]:
        return await self._request_tokens({
            "grant_type": "refresh_token",
            "client_id": self._client_id,
            "refresh_token": refresh_token,
        })

    async def _request_tokens(self, form: dict[str, str]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(self._token_endpoint, data=form)

        if response.status_code != 200:
            logger.warning(f"Token request failed ({response.status_code}): {response.text[:500]}")
            raise AuthError(f"Keycloak rejected the request: {response.status_code}")

        return response.json()

    def _evict_stale_logins(self) -> None:
        now = time.monotonic()
        stale = [state for state, (_, created) in self._pending_logins.items()
                 if now - created > _STATE_TTL_SECONDS]
        for state in stale:
            self._pending_logins.pop(state, None)
