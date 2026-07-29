import pytest

from common.constants import SYSTEM_APP_NAME
from data_agent.services.title_service import TitleService

USER_ID = "user-1"
SESSION_ID = "session-1"
TEMP_SESSION_ID = "temp-session-1"
USER_MESSAGE = "How many collections are in Milvus?"
TITLE = "Milvus collection count"


async def _async_iter(items):
    for item in items:
        yield item


def _final_event(mocker, text):
    event = mocker.MagicMock()
    event.is_final_response.return_value = True
    event.content.parts = [mocker.MagicMock(text=text)]
    return event


def _intermediate_event(mocker, text="partial"):
    event = mocker.MagicMock()
    event.is_final_response.return_value = False
    event.content.parts = [mocker.MagicMock(text=text)]
    return event


@pytest.fixture
def mock_session_store(mocker):
    store = mocker.AsyncMock()
    store.create_session.return_value = mocker.MagicMock(id=TEMP_SESSION_ID)
    mocker.patch(
        "data_agent.services.title_service.InMemorySessionService", return_value=store
    )
    return store


@pytest.fixture
def mock_runner(mocker):
    runner = mocker.MagicMock()
    runner.run_async = mocker.MagicMock(return_value=_async_iter([]))
    mocker.patch("data_agent.services.title_service.Runner", return_value=runner)
    return runner


@pytest.fixture
def mock_types(mocker):
    return mocker.patch("data_agent.services.title_service.types")


@pytest.fixture
def service(mock_session_store, mock_runner):
    return TitleService()


class TestInit:

    def test_builds_runner_with_the_system_app(self, mocker, mock_session_store):
        from data_agent.agents import system_app

        mock_runner_class = mocker.patch("data_agent.services.title_service.Runner")

        service = TitleService()

        mock_runner_class.assert_called_once_with(
            app=system_app,
            app_name=SYSTEM_APP_NAME,
            session_service=mock_session_store,
        )
        assert service._runner is mock_runner_class.return_value

    def test_uses_an_in_memory_session_store(self, service, mock_session_store):
        assert service._session_service is mock_session_store


class TestCreateSessionTitle:
    pytestmark = pytest.mark.asyncio

    async def test_returns_title_from_final_response(
        self, mocker, service, mock_runner, mock_types
    ):
        mock_runner.run_async.return_value = _async_iter([_final_event(mocker, TITLE)])

        result = await service.create_session_title(
            user_id=USER_ID, session_id=SESSION_ID, user_message=USER_MESSAGE
        )

        assert result == TITLE

    async def test_creates_a_temporary_system_session(
        self, mocker, service, mock_session_store, mock_runner, mock_types
    ):
        mock_runner.run_async.return_value = _async_iter([_final_event(mocker, TITLE)])

        await service.create_session_title(
            user_id=USER_ID, session_id=SESSION_ID, user_message=USER_MESSAGE
        )

        mock_session_store.create_session.assert_awaited_once_with(
            app_name=SYSTEM_APP_NAME, user_id=USER_ID
        )

    async def test_sends_the_user_message_to_the_runner(
        self, mocker, service, mock_runner, mock_types
    ):
        mock_runner.run_async.return_value = _async_iter([_final_event(mocker, TITLE)])

        await service.create_session_title(
            user_id=USER_ID, session_id=SESSION_ID, user_message=USER_MESSAGE
        )

        mock_types.Part.assert_called_once_with(text=USER_MESSAGE)
        mock_types.Content.assert_called_once_with(
            role="user", parts=[mock_types.Part.return_value]
        )
        mock_runner.run_async.assert_called_once_with(
            user_id=USER_ID,
            session_id=TEMP_SESSION_ID,
            new_message=mock_types.Content.return_value,
        )

    async def test_ignores_intermediate_events(
        self, mocker, service, mock_runner, mock_types
    ):
        mock_runner.run_async.return_value = _async_iter([
            _intermediate_event(mocker, "thinking"),
            _final_event(mocker, TITLE),
        ])

        result = await service.create_session_title(
            user_id=USER_ID, session_id=SESSION_ID, user_message=USER_MESSAGE
        )

        assert result == TITLE

    async def test_uses_the_last_part_of_the_final_response(
        self, mocker, service, mock_runner, mock_types
    ):
        event = _final_event(mocker, "ignored")
        event.content.parts = [
            mocker.MagicMock(text="first"),
            mocker.MagicMock(text="last"),
        ]
        mock_runner.run_async.return_value = _async_iter([event])

        result = await service.create_session_title(
            user_id=USER_ID, session_id=SESSION_ID, user_message=USER_MESSAGE
        )

        assert result == "last"

    async def test_keeps_the_last_final_response_when_several_arrive(
        self, mocker, service, mock_runner, mock_types
    ):
        mock_runner.run_async.return_value = _async_iter([
            _final_event(mocker, "first title"),
            _final_event(mocker, "second title"),
        ])

        result = await service.create_session_title(
            user_id=USER_ID, session_id=SESSION_ID, user_message=USER_MESSAGE
        )

        assert result == "second title"

    async def test_deletes_the_temporary_session_on_success(
        self, mocker, service, mock_session_store, mock_runner, mock_types
    ):
        mock_runner.run_async.return_value = _async_iter([_final_event(mocker, TITLE)])

        await service.create_session_title(
            user_id=USER_ID, session_id=SESSION_ID, user_message=USER_MESSAGE
        )

        mock_session_store.delete_session.assert_awaited_once_with(
            app_name=SYSTEM_APP_NAME, user_id=USER_ID, session_id=TEMP_SESSION_ID
        )

    async def test_raises_when_no_final_response_arrives(
        self, service, mock_runner, mock_types
    ):
        mock_runner.run_async.return_value = _async_iter([])

        with pytest.raises(ValueError, match="Couldn't create session title"):
            await service.create_session_title(
                user_id=USER_ID, session_id=SESSION_ID, user_message=USER_MESSAGE
            )

    async def test_raises_when_final_response_has_no_content(
        self, mocker, service, mock_runner, mock_types
    ):
        event = mocker.MagicMock()
        event.is_final_response.return_value = True
        event.content = None
        mock_runner.run_async.return_value = _async_iter([event])

        with pytest.raises(ValueError, match="Couldn't create session title"):
            await service.create_session_title(
                user_id=USER_ID, session_id=SESSION_ID, user_message=USER_MESSAGE
            )

    async def test_raises_when_final_response_has_no_parts(
        self, mocker, service, mock_runner, mock_types
    ):
        event = mocker.MagicMock()
        event.is_final_response.return_value = True
        event.content.parts = []
        mock_runner.run_async.return_value = _async_iter([event])

        with pytest.raises(ValueError, match="Couldn't create session title"):
            await service.create_session_title(
                user_id=USER_ID, session_id=SESSION_ID, user_message=USER_MESSAGE
            )

    async def test_raises_when_the_title_is_empty(
        self, mocker, service, mock_runner, mock_types
    ):
        mock_runner.run_async.return_value = _async_iter([_final_event(mocker, "")])

        with pytest.raises(ValueError, match="Couldn't create session title"):
            await service.create_session_title(
                user_id=USER_ID, session_id=SESSION_ID, user_message=USER_MESSAGE
            )

    async def test_temporary_session_is_left_behind_when_no_title_is_produced(
        self, service, mock_session_store, mock_runner, mock_types
    ):
        mock_runner.run_async.return_value = _async_iter([])

        with pytest.raises(ValueError):
            await service.create_session_title(
                user_id=USER_ID, session_id=SESSION_ID, user_message=USER_MESSAGE
            )

        mock_session_store.delete_session.assert_not_awaited()

    async def test_propagates_session_creation_errors(
        self, service, mock_session_store, mock_types
    ):
        mock_session_store.create_session.side_effect = RuntimeError("db down")

        with pytest.raises(RuntimeError, match="db down"):
            await service.create_session_title(
                user_id=USER_ID, session_id=SESSION_ID, user_message=USER_MESSAGE
            )

    async def test_propagates_runner_errors(
        self, mocker, service, mock_runner, mock_types
    ):
        mock_runner.run_async.side_effect = RuntimeError("model unavailable")

        with pytest.raises(RuntimeError, match="model unavailable"):
            await service.create_session_title(
                user_id=USER_ID, session_id=SESSION_ID, user_message=USER_MESSAGE
            )

    async def test_logs_the_failure(
        self, mocker, service, mock_session_store, mock_types
    ):
        mock_logger = mocker.patch("data_agent.services.title_service.logger")
        mock_session_store.create_session.side_effect = RuntimeError("db down")

        with pytest.raises(RuntimeError):
            await service.create_session_title(
                user_id=USER_ID, session_id=SESSION_ID, user_message=USER_MESSAGE
            )

        mock_logger.exception.assert_called_once()
