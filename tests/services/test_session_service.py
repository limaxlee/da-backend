from datetime import datetime, timezone

import pytest

from common.constants import APP_NAME, USER_AUTHOR
from data_agent.schemas import (
    CreateSessionResponse,
    CreateSessionTitleResponse,
    ListSessionsResponse,
    RenameSessionRequest,
    SessionInfo,
)
from data_agent.services.session_service import SessionService, create_session_store

USER_ID = "user-1"
SESSION_ID = "session-1"
NEW_SESSION_ID = "0123456789abcdef0123456789abcdef"
TITLE = "Milvus collection count"
LAST_UPDATE_TIME = 1_700_000_000.0
FIXED_DATETIME = datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)


def _part(mocker, text):
    return mocker.MagicMock(text=text)


def _event(mocker, author=USER_AUTHOR, parts=None, timestamp=LAST_UPDATE_TIME):
    event = mocker.MagicMock()
    event.author = author
    event.timestamp = timestamp
    if parts is None:
        event.content = None
    else:
        event.content.parts = parts
    return event


def _session(mocker, session_id=SESSION_ID, events=None, state=None):
    session = mocker.MagicMock()
    session.id = session_id
    session.app_name = APP_NAME
    session.user_id = USER_ID
    session.state = state if state is not None else {}
    session.events = events if events is not None else []
    session.last_update_time = LAST_UPDATE_TIME
    return session


@pytest.fixture
def mock_convert(mocker):
    return mocker.patch(
        "data_agent.services.session_service.convert_unix_to_datetime",
        return_value=FIXED_DATETIME,
    )


@pytest.fixture
def mock_event(mocker):
    return mocker.patch("data_agent.services.session_service.Event")


@pytest.fixture
def mock_event_actions(mocker):
    return mocker.patch("data_agent.services.session_service.EventActions")


@pytest.fixture
def sessions(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def titles(mocker):
    store = mocker.AsyncMock()
    store.create_session_title.return_value = TITLE
    return store


@pytest.fixture
def service(sessions, titles):
    return SessionService(sessions, titles)


class TestCreateSessionStore:

    def test_builds_an_asyncpg_url_from_settings(self, mocker):
        settings = mocker.patch("data_agent.services.session_service.SETTINGS")
        settings.session_db.host = "localhost"
        settings.session_db.port = 5432
        settings.session_db.name = "sessions"
        mock_store_class = mocker.patch(
            "data_agent.services.session_service.DatabaseSessionService"
        )

        store = create_session_store()

        mock_store_class.assert_called_once_with(
            db_url="postgresql+asyncpg://postgres@localhost:5432/sessions"
        )
        assert store is mock_store_class.return_value


class TestInit:

    def test_uses_the_application_app_name(self, service):
        assert service._app_name == APP_NAME

    def test_keeps_its_collaborators(self, service, sessions, titles):
        assert service._sessions is sessions
        assert service._titles is titles


class TestFindLastUserMessage:

    def test_returns_the_most_recent_user_message(self, mocker):
        session = _session(mocker, events=[
            _event(mocker, parts=[_part(mocker, "first")]),
            _event(mocker, parts=[_part(mocker, "second")]),
        ])

        assert SessionService._find_last_user_message(session) == "second"

    def test_skips_events_from_other_authors(self, mocker):
        session = _session(mocker, events=[
            _event(mocker, parts=[_part(mocker, "from user")]),
            _event(mocker, author="agent", parts=[_part(mocker, "from agent")]),
        ])

        assert SessionService._find_last_user_message(session) == "from user"

    def test_skips_events_without_content(self, mocker):
        session = _session(mocker, events=[
            _event(mocker, parts=[_part(mocker, "from user")]),
            _event(mocker, parts=None),
        ])

        assert SessionService._find_last_user_message(session) == "from user"

    def test_skips_events_without_parts(self, mocker):
        session = _session(mocker, events=[
            _event(mocker, parts=[_part(mocker, "from user")]),
            _event(mocker, parts=[]),
        ])

        assert SessionService._find_last_user_message(session) == "from user"

    def test_returns_the_last_non_empty_part(self, mocker):
        session = _session(mocker, events=[
            _event(mocker, parts=[
                _part(mocker, "text"),
                _part(mocker, "   "),
                _part(mocker, None),
            ])
        ])

        assert SessionService._find_last_user_message(session) == "text"

    def test_preserves_the_original_whitespace(self, mocker):
        session = _session(mocker, events=[
            _event(mocker, parts=[_part(mocker, "  padded  ")])
        ])

        assert SessionService._find_last_user_message(session) == "  padded  "

    def test_returns_none_when_there_are_no_events(self, mocker):
        assert SessionService._find_last_user_message(_session(mocker)) is None

    def test_returns_none_when_no_user_message_exists(self, mocker):
        session = _session(mocker, events=[
            _event(mocker, author="agent", parts=[_part(mocker, "from agent")])
        ])

        assert SessionService._find_last_user_message(session) is None


class TestListSessions:
    pytestmark = pytest.mark.asyncio

    async def test_maps_every_session(self, mocker, service, sessions, mock_convert):
        sessions.list_sessions.return_value = mocker.MagicMock(sessions=[
            _session(mocker, session_id="a"),
            _session(mocker, session_id="b"),
        ])

        result = await service.list_sessions(USER_ID)

        assert isinstance(result, ListSessionsResponse)
        assert [session.session_id for session in result.sessions] == ["a", "b"]

    async def test_queries_the_store_for_the_user(
        self, mocker, service, sessions, mock_convert
    ):
        sessions.list_sessions.return_value = mocker.MagicMock(sessions=[])

        await service.list_sessions(USER_ID)

        sessions.list_sessions.assert_awaited_once_with(
            app_name=APP_NAME, user_id=USER_ID
        )

    async def test_converts_the_last_update_time(
        self, mocker, service, sessions, mock_convert
    ):
        sessions.list_sessions.return_value = mocker.MagicMock(
            sessions=[_session(mocker)]
        )

        result = await service.list_sessions(USER_ID)

        mock_convert.assert_called_once_with(LAST_UPDATE_TIME)
        assert result.sessions[0].last_update_time == FIXED_DATETIME

    async def test_carries_session_state(self, mocker, service, sessions, mock_convert):
        sessions.list_sessions.return_value = mocker.MagicMock(
            sessions=[_session(mocker, state={"session_title": TITLE})]
        )

        result = await service.list_sessions(USER_ID)

        assert result.sessions[0].state == {"session_title": TITLE}

    async def test_returns_an_empty_response_when_the_user_has_no_sessions(
        self, mocker, service, sessions, mock_convert
    ):
        sessions.list_sessions.return_value = mocker.MagicMock(sessions=[])

        result = await service.list_sessions(USER_ID)

        assert result.sessions == []

    async def test_propagates_store_errors(self, service, sessions):
        sessions.list_sessions.side_effect = RuntimeError("db down")

        with pytest.raises(RuntimeError, match="db down"):
            await service.list_sessions(USER_ID)


class TestCreateSession:
    pytestmark = pytest.mark.asyncio

    @pytest.fixture
    def mock_uuid(self, mocker):
        mock_uuid = mocker.patch("data_agent.services.session_service.uuid")
        mock_uuid.uuid4.return_value.hex = NEW_SESSION_ID
        return mock_uuid

    async def test_creates_a_session_with_a_generated_id(
        self, mocker, service, sessions, mock_uuid
    ):
        sessions.create_session.return_value = _session(mocker, session_id=NEW_SESSION_ID)

        result = await service.create_session(USER_ID)

        sessions.create_session.assert_awaited_once_with(
            app_name=APP_NAME, user_id=USER_ID, session_id=NEW_SESSION_ID
        )
        assert isinstance(result, CreateSessionResponse)
        assert result.session_id == NEW_SESSION_ID

    async def test_returns_the_id_reported_by_the_store(
        self, mocker, service, sessions, mock_uuid
    ):
        sessions.create_session.return_value = _session(mocker, session_id="store-id")

        result = await service.create_session(USER_ID)

        assert result.session_id == "store-id"

    async def test_propagates_store_errors(self, service, sessions, mock_uuid):
        sessions.create_session.side_effect = RuntimeError("db down")

        with pytest.raises(RuntimeError, match="db down"):
            await service.create_session(USER_ID)


class TestCreateSessionTitle:
    pytestmark = pytest.mark.asyncio

    @pytest.fixture
    def session(self, mocker, sessions):
        session = _session(mocker, events=[
            _event(mocker, parts=[_part(mocker, "How many collections?")])
        ])
        sessions.get_session.return_value = session
        return session

    async def test_returns_the_generated_title(
        self, service, session, mock_event, mock_event_actions
    ):
        result = await service.create_session_title(USER_ID, SESSION_ID)

        assert isinstance(result, CreateSessionTitleResponse)
        assert result.session_title == TITLE

    async def test_loads_the_session(
        self, service, sessions, session, mock_event, mock_event_actions
    ):
        await service.create_session_title(USER_ID, SESSION_ID)

        sessions.get_session.assert_awaited_once_with(
            app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
        )

    async def test_passes_the_last_user_message_to_the_title_service(
        self, service, titles, session, mock_event, mock_event_actions
    ):
        await service.create_session_title(USER_ID, SESSION_ID)

        titles.create_session_title.assert_awaited_once_with(
            user_id=USER_ID, session_id=SESSION_ID, user_message="How many collections?"
        )

    async def test_appends_a_system_event_with_the_title(
        self, service, sessions, session, mock_event, mock_event_actions
    ):
        await service.create_session_title(USER_ID, SESSION_ID)

        mock_event_actions.assert_called_once_with(
            state_delta={"session_title": TITLE}
        )
        mock_event.assert_called_once_with(
            author="system", actions=mock_event_actions.return_value
        )
        sessions.append_event.assert_awaited_once_with(
            session, mock_event.return_value
        )

    async def test_raises_when_the_session_does_not_exist(
        self, service, sessions, titles
    ):
        sessions.get_session.return_value = None

        with pytest.raises(ValueError, match="does not have session"):
            await service.create_session_title(USER_ID, SESSION_ID)

        titles.create_session_title.assert_not_awaited()

    async def test_raises_when_the_session_has_no_user_message(
        self, mocker, service, sessions, titles
    ):
        sessions.get_session.return_value = _session(mocker, events=[])

        with pytest.raises(ValueError, match="has no user message"):
            await service.create_session_title(USER_ID, SESSION_ID)

        titles.create_session_title.assert_not_awaited()

    async def test_propagates_title_service_errors(
        self, service, titles, session
    ):
        titles.create_session_title.side_effect = RuntimeError("model unavailable")

        with pytest.raises(RuntimeError, match="model unavailable"):
            await service.create_session_title(USER_ID, SESSION_ID)

    async def test_propagates_append_event_errors(
        self, service, sessions, session, mock_event, mock_event_actions
    ):
        sessions.append_event.side_effect = RuntimeError("db down")

        with pytest.raises(RuntimeError, match="db down"):
            await service.create_session_title(USER_ID, SESSION_ID)


class TestRenameSessionTitle:
    pytestmark = pytest.mark.asyncio

    @pytest.fixture
    def request_body(self):
        return RenameSessionRequest(session_title="Renamed")

    @pytest.fixture
    def session(self, mocker, sessions):
        session = _session(mocker)
        sessions.get_session.return_value = session
        return session

    async def test_loads_the_session(
        self, service, sessions, session, request_body, mock_event, mock_event_actions
    ):
        await service.rename_session_title(USER_ID, SESSION_ID, request_body)

        sessions.get_session.assert_awaited_once_with(
            app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
        )

    async def test_appends_a_system_event_with_the_new_title(
        self, service, sessions, session, request_body, mock_event, mock_event_actions
    ):
        await service.rename_session_title(USER_ID, SESSION_ID, request_body)

        mock_event_actions.assert_called_once_with(
            state_delta={"session_title": "Renamed"}
        )
        mock_event.assert_called_once_with(
            author="system", actions=mock_event_actions.return_value
        )
        sessions.append_event.assert_awaited_once_with(
            session, mock_event.return_value
        )

    async def test_returns_none(
        self, service, session, request_body, mock_event, mock_event_actions
    ):
        result = await service.rename_session_title(USER_ID, SESSION_ID, request_body)

        assert result is None

    async def test_raises_when_the_session_does_not_exist(
        self, service, sessions, request_body
    ):
        sessions.get_session.return_value = None

        with pytest.raises(ValueError, match="does not have session"):
            await service.rename_session_title(USER_ID, SESSION_ID, request_body)

        sessions.append_event.assert_not_awaited()

    async def test_propagates_store_errors(
        self, service, sessions, session, request_body, mock_event, mock_event_actions
    ):
        sessions.append_event.side_effect = RuntimeError("db down")

        with pytest.raises(RuntimeError, match="db down"):
            await service.rename_session_title(USER_ID, SESSION_ID, request_body)


class TestGetSession:
    pytestmark = pytest.mark.asyncio

    async def test_returns_session_info(
        self, mocker, service, sessions, mock_convert
    ):
        sessions.get_session.return_value = _session(
            mocker, state={"session_title": TITLE}
        )

        result = await service.get_session(USER_ID, SESSION_ID)

        assert isinstance(result, SessionInfo)
        assert result.session_id == SESSION_ID
        assert result.app_name == APP_NAME
        assert result.user_id == USER_ID
        assert result.state == {"session_title": TITLE}
        assert result.last_update_time == FIXED_DATETIME

    async def test_loads_the_session_for_the_user(
        self, mocker, service, sessions, mock_convert
    ):
        sessions.get_session.return_value = _session(mocker)

        await service.get_session(USER_ID, SESSION_ID)

        sessions.get_session.assert_awaited_once_with(
            app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
        )

    async def test_converts_every_event_timestamp(
        self, mocker, service, sessions, mock_convert
    ):
        events = [_event(mocker), _event(mocker)]
        sessions.get_session.return_value = _session(mocker, events=events)

        await service.get_session(USER_ID, SESSION_ID)

        assert [event.timestamp for event in events] == [FIXED_DATETIME] * 2
        assert mock_convert.call_count == 3

    async def test_raises_when_the_session_does_not_exist(self, service, sessions):
        sessions.get_session.return_value = None

        with pytest.raises(ValueError, match="does not have session"):
            await service.get_session(USER_ID, SESSION_ID)

    async def test_propagates_store_errors(self, service, sessions):
        sessions.get_session.side_effect = RuntimeError("db down")

        with pytest.raises(RuntimeError, match="db down"):
            await service.get_session(USER_ID, SESSION_ID)


class TestDeleteSession:
    pytestmark = pytest.mark.asyncio

    async def test_deletes_the_session(self, service, sessions):
        await service.delete_session(USER_ID, SESSION_ID)

        sessions.delete_session.assert_awaited_once_with(
            app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
        )

    async def test_returns_none(self, service, sessions):
        assert await service.delete_session(USER_ID, SESSION_ID) is None

    async def test_propagates_store_errors(self, service, sessions):
        sessions.delete_session.side_effect = RuntimeError("db down")

        with pytest.raises(RuntimeError, match="db down"):
            await service.delete_session(USER_ID, SESSION_ID)
