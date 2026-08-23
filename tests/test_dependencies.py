import pytest
from fastapi import HTTPException

from data_agent import dependencies
from data_agent.schemas import CurrentUser
from data_agent.services import AuthError, current_fabrix_token


@pytest.fixture
def current_user():
    return CurrentUser(
        id="user-1",
        email="user@samsung.com",
        name="User One",
        token="raw-token",
        expires_at=1_700_000_000,
    )


def test_get_object_storage(mocker):
    storage_cls = mocker.patch.object(dependencies, "ObjectStorage")
    dependencies.get_object_storage.cache_clear()
    try:
        first = dependencies.get_object_storage()

        assert first is storage_cls.return_value
        assert dependencies.get_object_storage() is first
        storage_cls.assert_called_once_with()
    finally:
        dependencies.get_object_storage.cache_clear()


def test_get_session_store(mocker):
    create_store = mocker.patch.object(dependencies, "create_session_store")
    dependencies.get_session_store.cache_clear()
    try:
        first = dependencies.get_session_store()

        assert first is create_store.return_value
        assert dependencies.get_session_store() is first
        create_store.assert_called_once_with()
    finally:
        dependencies.get_session_store.cache_clear()


def test_get_db_session_service(mocker):
    service_cls = mocker.patch.object(dependencies, "DBSessionService")
    system_runner_cls = mocker.patch.object(dependencies, "SystemRunner")
    get_session_store = mocker.patch.object(dependencies, "get_session_store")
    dependencies.get_db_session_service.cache_clear()
    try:
        first = dependencies.get_db_session_service()

        assert first is service_cls.return_value
        assert dependencies.get_db_session_service() is first
        service_cls.assert_called_once_with(
            session_service=get_session_store.return_value,
            system_runner=system_runner_cls.return_value,
        )
    finally:
        dependencies.get_db_session_service.cache_clear()


def test_get_agent_runner(mocker):
    runner_cls = mocker.patch.object(dependencies, "AgentRunner")
    artifact_cls = mocker.patch.object(dependencies, "OSArtifactService")
    get_session_store = mocker.patch.object(dependencies, "get_session_store")
    get_object_storage = mocker.patch.object(dependencies, "get_object_storage")
    dependencies.get_agent_runner.cache_clear()
    try:
        first = dependencies.get_agent_runner()

        assert first is runner_cls.return_value
        assert dependencies.get_agent_runner() is first
        artifact_cls.assert_called_once_with(storage=get_object_storage.return_value)
        runner_cls.assert_called_once_with(
            session_service=get_session_store.return_value,
            artifact_service=artifact_cls.return_value,
        )
    finally:
        dependencies.get_agent_runner.cache_clear()


def test_get_auth_service(mocker):
    service_cls = mocker.patch.object(dependencies, "AuthService")
    dependencies.get_auth_service.cache_clear()
    try:
        first = dependencies.get_auth_service()

        assert first is service_cls.return_value
        assert dependencies.get_auth_service() is first
        service_cls.assert_called_once_with()
    finally:
        dependencies.get_auth_service.cache_clear()


@pytest.mark.asyncio
async def test_get_current_user(mocker, current_user):
    auth_service = mocker.Mock(user_from_token=mocker.Mock(return_value=current_user))
    credentials = mocker.Mock(credentials="raw-token")

    result = await dependencies.get_current_user(credentials, auth_service)

    assert result is current_user
    auth_service.user_from_token.assert_called_once_with("raw-token")
    assert current_fabrix_token.get() == "raw-token"

    with pytest.raises(HTTPException) as missing:
        await dependencies.get_current_user(None, auth_service)
    assert missing.value.status_code == 401

    auth_service.user_from_token.side_effect = AuthError("expired")
    with pytest.raises(HTTPException) as invalid:
        await dependencies.get_current_user(credentials, auth_service)
    assert invalid.value.status_code == 401


@pytest.mark.asyncio
async def test_require_path_user(current_user):
    assert await dependencies.require_path_user("user-1", current_user) is current_user

    with pytest.raises(HTTPException) as forbidden:
        await dependencies.require_path_user("someone-else", current_user)
    assert forbidden.value.status_code == 403
