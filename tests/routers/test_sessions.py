from datetime import datetime, timezone

import pytest
from fastapi import status

from common.constants import APP_NAME
from data_agent.schemas import (
    CreateSessionResponse,
    CreateSessionTitleResponse,
    ListSessionsResponse,
    RenameSessionRequest,
    SessionInfo,
)

USER_ID = "user-1"
SESSION_ID = "session-1"
TITLE = "Milvus collection count"
LAST_UPDATE_TIME = datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)

SESSIONS_URL = f"/apps/users/{USER_ID}/sessions"
SESSION_URL = f"{SESSIONS_URL}/{SESSION_ID}"
TITLE_URL = f"{SESSION_URL}/title"


@pytest.fixture
def session_service(mocker):
    return mocker.patch(
        "data_agent.routers.sessions.session_service", new_callable=mocker.AsyncMock
    )


def _session_info(session_id=SESSION_ID, state=None):
    return SessionInfo(
        session_id=session_id,
        app_name=APP_NAME,
        user_id=USER_ID,
        state=state or {},
        events=[],
        last_update_time=LAST_UPDATE_TIME,
    )


class TestListSessions:

    def test_returns_the_session_list(self, client, session_service):
        session_service.list_sessions.return_value = ListSessionsResponse(
            sessions=[_session_info(state={"session_title": TITLE})]
        )

        response = client.get(SESSIONS_URL)

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"sessions": [{
            "session_id": SESSION_ID,
            "app_name": APP_NAME,
            "user_id": USER_ID,
            "state": {"session_title": TITLE},
            "events": [],
            "last_update_time": "2023-11-14T22:13:20Z",
        }]}

    def test_delegates_to_the_service(self, client, session_service):
        session_service.list_sessions.return_value = ListSessionsResponse()

        client.get(SESSIONS_URL)

        session_service.list_sessions.assert_awaited_once_with(user_id=USER_ID)

    def test_returns_an_empty_list(self, client, session_service):
        session_service.list_sessions.return_value = ListSessionsResponse()

        response = client.get(SESSIONS_URL)

        assert response.json() == {"sessions": []}

    def test_maps_failures_to_500(self, client, session_service):
        session_service.list_sessions.side_effect = RuntimeError("db down")

        response = client.get(SESSIONS_URL)

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json() == {"detail": "db down"}

    def test_maps_value_errors_to_500(self, client, session_service):
        session_service.list_sessions.side_effect = ValueError("bad user")

        response = client.get(SESSIONS_URL)

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestCreateSession:

    def test_returns_the_new_session_id(self, client, session_service):
        session_service.create_session.return_value = CreateSessionResponse(
            session_id=SESSION_ID
        )

        response = client.post(SESSIONS_URL)

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"session_id": SESSION_ID}

    def test_delegates_to_the_service(self, client, session_service):
        session_service.create_session.return_value = CreateSessionResponse(
            session_id=SESSION_ID
        )

        client.post(SESSIONS_URL)

        session_service.create_session.assert_awaited_once_with(user_id=USER_ID)

    def test_maps_failures_to_500(self, client, session_service):
        session_service.create_session.side_effect = RuntimeError("db down")

        response = client.post(SESSIONS_URL)

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json() == {"detail": "db down"}


class TestCreateSessionTitle:

    def test_returns_the_generated_title(self, client, session_service):
        session_service.create_session_title.return_value = CreateSessionTitleResponse(
            session_title=TITLE
        )

        response = client.post(TITLE_URL)

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {"session_title": TITLE}

    def test_delegates_to_the_service(self, client, session_service):
        session_service.create_session_title.return_value = CreateSessionTitleResponse(
            session_title=TITLE
        )

        client.post(TITLE_URL)

        session_service.create_session_title.assert_awaited_once_with(
            USER_ID, SESSION_ID
        )

    def test_maps_value_errors_to_400(self, client, session_service):
        session_service.create_session_title.side_effect = ValueError(
            "session has no user message"
        )

        response = client.post(TITLE_URL)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json() == {"detail": "session has no user message"}

    def test_maps_other_failures_to_500(self, client, session_service):
        session_service.create_session_title.side_effect = RuntimeError("model down")

        response = client.post(TITLE_URL)

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json() == {"detail": "model down"}


class TestRenameSessionTitle:

    def test_accepts_the_title_as_a_query_parameter(self, client, session_service):
        response = client.patch(TITLE_URL, params={"session_title": "Renamed"})

        assert response.status_code == status.HTTP_200_OK
        assert response.json() is None

    def test_passes_a_rename_request_to_the_service(self, client, session_service):
        client.patch(TITLE_URL, params={"session_title": "Renamed"})

        session_service.rename_session_title.assert_awaited_once()
        user_id, session_id, request = session_service.rename_session_title.await_args.args
        assert (user_id, session_id) == (USER_ID, SESSION_ID)
        assert isinstance(request, RenameSessionRequest)
        assert request.session_title == "Renamed"

    def test_rejects_a_json_body(self, client, session_service):
        response = client.patch(TITLE_URL, json={"session_title": "Renamed"})

        assert response.status_code == 422
        session_service.rename_session_title.assert_not_awaited()

    def test_requires_the_title(self, client, session_service):
        response = client.patch(TITLE_URL)

        assert response.status_code == 422
        session_service.rename_session_title.assert_not_awaited()

    def test_maps_value_errors_to_400(self, client, session_service):
        session_service.rename_session_title.side_effect = ValueError(
            "does not have session"
        )

        response = client.patch(TITLE_URL, params={"session_title": "Renamed"})

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json() == {"detail": "does not have session"}

    def test_maps_other_failures_to_500(self, client, session_service):
        session_service.rename_session_title.side_effect = RuntimeError("db down")

        response = client.patch(TITLE_URL, params={"session_title": "Renamed"})

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestGetSession:

    def test_returns_the_session(self, client, session_service):
        session_service.get_session.return_value = _session_info()

        response = client.get(SESSION_URL)

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["session_id"] == SESSION_ID
        assert response.json()["last_update_time"] == "2023-11-14T22:13:20Z"

    def test_delegates_to_the_service(self, client, session_service):
        session_service.get_session.return_value = _session_info()

        client.get(SESSION_URL)

        session_service.get_session.assert_awaited_once_with(
            user_id=USER_ID, session_id=SESSION_ID
        )

    def test_maps_value_errors_to_400(self, client, session_service):
        session_service.get_session.side_effect = ValueError("does not have session")

        response = client.get(SESSION_URL)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.json() == {"detail": "does not have session"}

    def test_maps_other_failures_to_500(self, client, session_service):
        session_service.get_session.side_effect = RuntimeError("db down")

        response = client.get(SESSION_URL)

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestDeleteSession:

    def test_returns_200(self, client, session_service):
        response = client.delete(SESSION_URL)

        assert response.status_code == status.HTTP_200_OK
        assert response.json() is None

    def test_delegates_to_the_service(self, client, session_service):
        client.delete(SESSION_URL)

        session_service.delete_session.assert_awaited_once_with(
            user_id=USER_ID, session_id=SESSION_ID
        )

    def test_maps_failures_to_500(self, client, session_service):
        session_service.delete_session.side_effect = RuntimeError("db down")

        response = client.delete(SESSION_URL)

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json() == {"detail": "db down"}

    def test_maps_value_errors_to_500(self, client, session_service):
        session_service.delete_session.side_effect = ValueError("does not have session")

        response = client.delete(SESSION_URL)

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


class TestRouting:

    def test_routes_are_mounted_under_the_apps_prefix(self, client, session_service):
        session_service.list_sessions.return_value = ListSessionsResponse()

        assert client.get(SESSIONS_URL).status_code == status.HTTP_200_OK
        assert client.get(f"/users/{USER_ID}/sessions").status_code == (
            status.HTTP_404_NOT_FOUND
        )

    def test_url_encoded_identifiers_reach_the_service(self, client, session_service):
        session_service.get_session.return_value = _session_info()

        client.get(f"/apps/users/user%20one/sessions/{SESSION_ID}")

        session_service.get_session.assert_awaited_once_with(
            user_id="user one", session_id=SESSION_ID
        )
