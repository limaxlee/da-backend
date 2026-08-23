import pytest

from common.config import SETTINGS
from data_agent.routers.auth import _redirect_uri
from data_agent.services import AuthError


def test__redirect_uri(mocker):
    request = mocker.Mock(url_for=mocker.Mock(return_value="http://testserver/auth/callback"))

    mocker.patch.object(SETTINGS.auth, "redirect_uri", "")
    assert _redirect_uri(request) == "http://testserver/auth/callback"

    mocker.patch.object(SETTINGS.auth, "redirect_uri", "https://proxy/auth/callback")
    assert _redirect_uri(request) == "https://proxy/auth/callback"


def test_login(client, auth_service):
    auth_service.build_login_url.return_value = "https://keycloak/auth?state=abc"

    response = client.get("/auth/login", follow_redirects=False)

    assert response.status_code == 307
    assert response.headers["location"] == "https://keycloak/auth?state=abc"
    auth_service.build_login_url.assert_called_once()


def test_callback_json_mode(client, auth_service, mocker):
    mocker.patch.object(SETTINGS.auth, "frontend_url", "")
    tokens = {"access_token": "at", "refresh_token": "rt", "expires_in": 300, "refresh_expires_in": 1800}
    auth_service.exchange_code.return_value = tokens

    response = client.get("/auth/callback", params={"code": "code-1", "state": "state-1"})
    assert response.status_code == 200
    assert response.json()["access_token"] == "at"
    assert auth_service.exchange_code.await_args.args[:2] == ("code-1", "state-1")

    assert client.get("/auth/callback", params={"error": "access_denied"}).status_code == 401
    assert client.get("/auth/callback", params={"code": "code-1"}).status_code == 400

    auth_service.exchange_code.side_effect = AuthError("expired state")
    assert client.get("/auth/callback", params={"code": "c", "state": "s"}).status_code == 401


def test_callback_redirects_to_frontend(client, auth_service, mocker):
    mocker.patch.object(SETTINGS.auth, "frontend_url", "http://localhost:3000")
    tokens = {"access_token": "at", "refresh_token": "rt", "expires_in": 4200, "refresh_expires_in": 14854}
    auth_service.exchange_code.return_value = tokens

    response = client.get(
        "/auth/callback", params={"code": "code-1", "state": "state-1"}, follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["location"] == (
        "http://localhost:3000/auth/callback"
        "#access_token=at&refresh_token=rt&expires_in=4200&refresh_expires_in=14854"
    )


def test_callback_redirects_errors_to_frontend(client, auth_service, mocker):
    mocker.patch.object(SETTINGS.auth, "frontend_url", "http://localhost:3000/")

    response = client.get("/auth/callback", params={"error": "access_denied"}, follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "http://localhost:3000/auth/callback#error=access_denied"

    response = client.get("/auth/callback", params={"code": "only-code"}, follow_redirects=False)
    assert response.headers["location"].endswith("#error=invalid_request")

    auth_service.exchange_code.side_effect = AuthError("expired state")
    response = client.get("/auth/callback", params={"code": "c", "state": "s"}, follow_redirects=False)
    assert response.headers["location"].endswith("#error=login_expired")


def test_refresh(client, auth_service):
    tokens = {"access_token": "new-at", "refresh_token": "new-rt", "expires_in": 300}
    auth_service.refresh_tokens.return_value = tokens

    response = client.post("/auth/refresh", json={"refresh_token": "rt-1"})
    assert response.status_code == 200
    assert response.json()["access_token"] == "new-at"
    auth_service.refresh_tokens.assert_awaited_once_with("rt-1")

    auth_service.refresh_tokens.side_effect = AuthError("session ended")
    assert client.post("/auth/refresh", json={"refresh_token": "rt-1"}).status_code == 401


def test_me(client, current_user):
    response = client.get("/auth/me")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == current_user.id
    assert body["email"] == current_user.email
    assert body["permissions"] == current_user.permissions
    assert "token" not in body
