from datetime import datetime, timezone

from data_agent.schemas import (
    CreateSessionResponse, CreateSessionTitleResponse, ListSessionsResponse, SessionInfo
)

LAST_UPDATE = datetime(2026, 8, 23, tzinfo=timezone.utc)


def _session_info(session_id="s1"):
    return SessionInfo(
        session_id=session_id,
        app_name="data_agent",
        user_id="user-1",
        state={"session_title": "Title"},
        events=[],
        last_update_time=LAST_UPDATE,
    )


def test_list_sessions(client, db_session_service):
    db_session_service.list_sessions.return_value = ListSessionsResponse(sessions=[_session_info()])

    response = client.get("/apps/users/user-1/sessions")

    assert response.status_code == 200
    assert response.json()["sessions"][0]["session_id"] == "s1"
    db_session_service.list_sessions.assert_awaited_once_with(user_id="user-1")

    db_session_service.list_sessions.side_effect = RuntimeError("db down")
    assert client.get("/apps/users/user-1/sessions").status_code == 500


def test_create_session(client, db_session_service):
    db_session_service.create_session.return_value = CreateSessionResponse(session_id="new-session")

    response = client.post("/apps/users/user-1/sessions")

    assert response.status_code == 200
    assert response.json() == {"session_id": "new-session"}
    db_session_service.create_session.assert_awaited_once_with(user_id="user-1")

    db_session_service.create_session.side_effect = RuntimeError("db down")
    assert client.post("/apps/users/user-1/sessions").status_code == 500


def test_create_session_title(client, db_session_service):
    db_session_service.create_session_title.return_value = CreateSessionTitleResponse(session_title="Generated")

    response = client.post("/apps/users/user-1/sessions/s1/title")

    assert response.status_code == 200
    assert response.json() == {"session_title": "Generated"}
    db_session_service.create_session_title.assert_awaited_once_with("user-1", "s1")

    db_session_service.create_session_title.side_effect = ValueError("no user message")
    assert client.post("/apps/users/user-1/sessions/s1/title").status_code == 400

    db_session_service.create_session_title.side_effect = RuntimeError("db down")
    assert client.post("/apps/users/user-1/sessions/s1/title").status_code == 500


def test_rename_session_title(client, db_session_service):
    response = client.patch("/apps/users/user-1/sessions/s1/title", params={"session_title": "Renamed"})

    assert response.status_code == 200
    args = db_session_service.rename_session_title.await_args.args
    assert args[:2] == ("user-1", "s1")
    assert args[2].session_title == "Renamed"

    db_session_service.rename_session_title.side_effect = ValueError("not found")
    assert client.patch(
        "/apps/users/user-1/sessions/s1/title", params={"session_title": "Renamed"}
    ).status_code == 400

    db_session_service.rename_session_title.side_effect = RuntimeError("db down")
    assert client.patch(
        "/apps/users/user-1/sessions/s1/title", params={"session_title": "Renamed"}
    ).status_code == 500


def test_get_session(client, db_session_service):
    db_session_service.get_session.return_value = _session_info()

    response = client.get("/apps/users/user-1/sessions/s1")

    assert response.status_code == 200
    assert response.json()["session_id"] == "s1"
    db_session_service.get_session.assert_awaited_once_with(user_id="user-1", session_id="s1")

    db_session_service.get_session.side_effect = ValueError("not found")
    assert client.get("/apps/users/user-1/sessions/s1").status_code == 400

    db_session_service.get_session.side_effect = RuntimeError("db down")
    assert client.get("/apps/users/user-1/sessions/s1").status_code == 500


def test_delete_session(client, db_session_service):
    response = client.delete("/apps/users/user-1/sessions/s1")

    assert response.status_code == 200
    db_session_service.delete_session.assert_awaited_once_with(user_id="user-1", session_id="s1")

    db_session_service.delete_session.side_effect = RuntimeError("db down")
    assert client.delete("/apps/users/user-1/sessions/s1").status_code == 500
