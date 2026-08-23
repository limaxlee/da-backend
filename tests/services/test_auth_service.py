import time
from urllib.parse import parse_qs, urlparse

import pytest
from jwt import InvalidTokenError

from common.config import SETTINGS
from data_agent.services.auth_service import AuthError, AuthService


@pytest.fixture
def service(mocker):
    mocker.patch("data_agent.services.auth_service.PyJWKClient")
    return AuthService()


class TestAuthService:
    def test_verify_token(self, mocker, service):
        signing_key = mocker.Mock(key="public-key")
        service._jwks.get_signing_key_from_jwt = mocker.Mock(return_value=signing_key)
        claims = {"sub": "user-1", "exp": 123}
        decode = mocker.patch("data_agent.services.auth_service.jwt.decode", return_value=claims)

        assert service.verify_token("raw-token") == claims
        decode.assert_called_once_with(
            "raw-token",
            "public-key",
            algorithms=["RS256"],
            issuer=SETTINGS.auth.issuer.rstrip("/"),
            leeway=30,
            options={"verify_aud": False},
        )

        decode.side_effect = InvalidTokenError("expired")
        with pytest.raises(AuthError):
            service.verify_token("raw-token")

    def test_user_from_token(self, mocker, service):
        claims = {
            "sub": "user-1",
            "user_email": "user@samsung.com",
            "en_name": "User One",
            "tenant_id": "tenant-1",
            "permission": ["chat"],
            "exp": 1_700_000_000,
        }
        mocker.patch.object(service, "verify_token", return_value=claims)

        user = service.user_from_token("raw-token")

        assert user.id == "user-1"
        assert user.email == "user@samsung.com"
        assert user.name == "User One"
        assert user.tenant_id == "tenant-1"
        assert user.permissions == ["chat"]
        assert user.token == "raw-token"
        assert user.expires_at == 1_700_000_000

    def test_build_login_url(self, service):
        url = service.build_login_url("https://backend/auth/callback")

        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        assert url.startswith(f"{SETTINGS.auth.issuer.rstrip('/')}/protocol/openid-connect/auth?")
        assert query["response_type"] == ["code"]
        assert query["client_id"] == [SETTINGS.auth.client_id]
        assert query["redirect_uri"] == ["https://backend/auth/callback"]
        assert query["code_challenge_method"] == ["S256"]
        assert query["code_challenge"]

        state = query["state"][0]
        assert state in service._pending_logins

    @pytest.mark.asyncio
    async def test_exchange_code(self, mocker, service):
        tokens = {"access_token": "at", "expires_in": 300}
        request_tokens = mocker.patch.object(
            service, "_request_tokens", mocker.AsyncMock(return_value=tokens)
        )
        service._pending_logins["state-1"] = ("verifier-1", time.monotonic())

        result = await service.exchange_code("code-1", "state-1", "https://backend/auth/callback")

        assert result == tokens
        assert "state-1" not in service._pending_logins
        request_tokens.assert_awaited_once_with({
            "grant_type": "authorization_code",
            "client_id": SETTINGS.auth.client_id,
            "code": "code-1",
            "redirect_uri": "https://backend/auth/callback",
            "code_verifier": "verifier-1",
        })

        with pytest.raises(AuthError):
            await service.exchange_code("code-1", "unknown-state", "https://backend/auth/callback")

        service._pending_logins["state-2"] = ("verifier-2", time.monotonic() - 601)
        with pytest.raises(AuthError):
            await service.exchange_code("code-1", "state-2", "https://backend/auth/callback")

    @pytest.mark.asyncio
    async def test_refresh_tokens(self, mocker, service):
        tokens = {"access_token": "at", "expires_in": 300}
        request_tokens = mocker.patch.object(
            service, "_request_tokens", mocker.AsyncMock(return_value=tokens)
        )

        assert await service.refresh_tokens("refresh-1") == tokens
        request_tokens.assert_awaited_once_with({
            "grant_type": "refresh_token",
            "client_id": SETTINGS.auth.client_id,
            "refresh_token": "refresh-1",
        })

    @pytest.mark.asyncio
    async def test__request_tokens(self, mocker, service):
        response = mocker.Mock(status_code=200, json=mocker.Mock(return_value={"access_token": "at"}))
        http_client = mocker.Mock(post=mocker.AsyncMock(return_value=response))
        client_cls = mocker.patch("data_agent.services.auth_service.httpx.AsyncClient")
        client_cls.return_value.__aenter__.return_value = http_client

        form = {"grant_type": "refresh_token"}
        assert await service._request_tokens(form) == {"access_token": "at"}
        http_client.post.assert_awaited_once_with(service._token_endpoint, data=form)

        response.status_code = 401
        response.text = "unauthorized"
        with pytest.raises(AuthError):
            await service._request_tokens(form)

    def test__evict_stale_logins(self, service):
        now = time.monotonic()
        service._pending_logins["fresh"] = ("verifier", now)
        service._pending_logins["stale"] = ("verifier", now - 601)

        service._evict_stale_logins()

        assert "fresh" in service._pending_logins
        assert "stale" not in service._pending_logins
