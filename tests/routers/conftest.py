import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from data_agent.dependencies import (
    get_agent_runner, get_auth_service, get_current_user, get_db_session_service, require_path_user
)
from data_agent.routers import router
from data_agent.schemas import CurrentUser


@pytest.fixture
def current_user():
    return CurrentUser(
        id="user-1",
        email="user@samsung.com",
        name="User One",
        tenant_id="tenant-1",
        permissions=["chat"],
        token="raw-token",
        expires_at=1_700_000_000,
    )


@pytest.fixture
def agent_runner(mocker):
    return mocker.Mock(run=mocker.AsyncMock())


@pytest.fixture
def db_session_service(mocker):
    return mocker.Mock(
        list_sessions=mocker.AsyncMock(),
        create_session=mocker.AsyncMock(),
        create_session_title=mocker.AsyncMock(),
        rename_session_title=mocker.AsyncMock(),
        get_session=mocker.AsyncMock(),
        delete_session=mocker.AsyncMock(),
    )


@pytest.fixture
def auth_service(mocker):
    return mocker.Mock(
        build_login_url=mocker.Mock(),
        exchange_code=mocker.AsyncMock(),
        refresh_tokens=mocker.AsyncMock(),
    )


@pytest.fixture
def app(current_user, agent_runner, db_session_service, auth_service):
    application = FastAPI()
    application.include_router(router)
    application.dependency_overrides[get_current_user] = lambda: current_user
    application.dependency_overrides[require_path_user] = lambda: current_user
    application.dependency_overrides[get_agent_runner] = lambda: agent_runner
    application.dependency_overrides[get_db_session_service] = lambda: db_session_service
    application.dependency_overrides[get_auth_service] = lambda: auth_service
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client
