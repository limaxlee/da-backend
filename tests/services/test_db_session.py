from types import SimpleNamespace

import pytest

from common.config import SETTINGS
from common.constants import APP_NAME
from data_agent.schemas import RenameSessionRequest
from data_agent.services.db_session import DBSessionService, create_session_store
from data_agent.utils import convert_unix_to_datetime

TIMESTAMP = 1_700_000_000.0


def _user_event(text):
    return SimpleNamespace(author="user", content=SimpleNamespace(parts=[SimpleNamespace(text=text)]))


def _model_event(text="model answer"):
    return SimpleNamespace(author="root_agent", content=SimpleNamespace(parts=[SimpleNamespace(text=text)]))


def _session(session_id="s1", events=None):
    return SimpleNamespace(
        id=session_id,
        app_name=APP_NAME,
        user_id="u1",
        state={"session_title": "Old"},
        events=events if events is not None else [],
        last_update_time=TIMESTAMP,
    )


@pytest.fixture
def session_service(mocker):
    return mocker.Mock(
        list_sessions=mocker.AsyncMock(),
        create_session=mocker.AsyncMock(),
        get_session=mocker.AsyncMock(),
        append_event=mocker.AsyncMock(),
        delete_session=mocker.AsyncMock(),
    )


@pytest.fixture
def system_runner(mocker):
    return mocker.Mock(create_session_title=mocker.AsyncMock(return_value="Generated Title"))


@pytest.fixture
def service(session_service, system_runner):
    return DBSessionService(session_service=session_service, system_runner=system_runner)


def test_create_session_store(mocker):
    store_cls = mocker.patch("data_agent.services.db_session.DatabaseSessionService")

    store = create_session_store()

    assert store is store_cls.return_value
    db = SETTINGS.session_db
    store_cls.assert_called_once_with(db_url=f"postgresql+asyncpg://postgres@{db.host}:{db.port}/{db.name}")


class TestDBSessionService:
    def test__find_last_user_message(self, service):
        session = _session(events=[
            _user_event("first question"),
            _model_event(),
            _user_event("  latest question  "),
            _model_event(),
        ])
        assert service._find_last_user_message(session) == "  latest question  "

        assert service._find_last_user_message(_session(events=[_model_event()])) is None

    @pytest.mark.asyncio
    async def test_list_sessions(self, service, session_service):
        session_service.list_sessions.return_value = SimpleNamespace(sessions=[_session()])

        response = await service.list_sessions(user_id="u1")

        session_service.list_sessions.assert_awaited_once_with(app_name=APP_NAME, user_id="u1")
        assert len(response.sessions) == 1
        info = response.sessions[0]
        assert info.session_id == "s1"
        assert info.app_name == APP_NAME
        assert info.user_id == "u1"
        assert info.last_update_time == convert_unix_to_datetime(TIMESTAMP)

        session_service.list_sessions.side_effect = RuntimeError("db down")
        with pytest.raises(RuntimeError):
            await service.list_sessions(user_id="u1")

    @pytest.mark.asyncio
    async def test_create_session(self, service, session_service):
        session_service.create_session.return_value = _session(session_id="new-session")

        response = await service.create_session(user_id="u1")

        assert response.session_id == "new-session"
        kwargs = session_service.create_session.await_args.kwargs
        assert kwargs["app_name"] == APP_NAME
        assert kwargs["user_id"] == "u1"
        assert kwargs["session_id"]

    @pytest.mark.asyncio
    async def test_create_session_title(self, service, session_service, system_runner):
        session = _session(events=[_user_event("what is in the bucket?")])
        session_service.get_session.return_value = session

        response = await service.create_session_title(user_id="u1", session_id="s1")

        assert response.session_title == "Generated Title"
        system_runner.create_session_title.assert_awaited_once_with(
            user_id="u1", session_id="s1", user_message="what is in the bucket?"
        )
        appended_session, event = session_service.append_event.await_args.args
        assert appended_session is session
        assert event.actions.state_delta == {"session_title": "Generated Title"}

        session_service.get_session.return_value = None
        with pytest.raises(ValueError):
            await service.create_session_title(user_id="u1", session_id="s1")

    @pytest.mark.asyncio
    async def test_rename_session_title(self, service, session_service):
        session = _session()
        session_service.get_session.return_value = session

        await service.rename_session_title(user_id="u1", session_id="s1", request=RenameSessionRequest(session_title="New Title"))

        appended_session, event = session_service.append_event.await_args.args
        assert appended_session is session
        assert event.actions.state_delta == {"session_title": "New Title"}

        session_service.get_session.return_value = None
        with pytest.raises(ValueError):
            await service.rename_session_title(user_id="u1", session_id="s1", request=RenameSessionRequest(session_title="New Title"))

    @pytest.mark.asyncio
    async def test_get_session(self, service, session_service):
        session = _session(events=[SimpleNamespace(author="user", content=None, timestamp=TIMESTAMP)])
        session_service.get_session.return_value = session

        info = await service.get_session(user_id="u1", session_id="s1")

        session_service.get_session.assert_awaited_once_with(app_name=APP_NAME, user_id="u1", session_id="s1")
        assert info.session_id == "s1"
        assert info.last_update_time == convert_unix_to_datetime(TIMESTAMP)
        assert info.events[0].timestamp == convert_unix_to_datetime(TIMESTAMP)

        session_service.get_session.return_value = None
        with pytest.raises(ValueError):
            await service.get_session(user_id="u1", session_id="s1")

    @pytest.mark.asyncio
    async def test_delete_session(self, service, session_service):
        await service.delete_session(user_id="u1", session_id="s1")

        session_service.delete_session.assert_awaited_once_with(app_name=APP_NAME, user_id="u1", session_id="s1")

        session_service.delete_session.side_effect = RuntimeError("db down")
        with pytest.raises(RuntimeError):
            await service.delete_session(user_id="u1", session_id="s1")
