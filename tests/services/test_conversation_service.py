from datetime import datetime, timezone

import pytest

from common.constants import APP_NAME
from data_agent.schemas import RunAgentRequest, RunAgentResponse
from data_agent.services.conversation_service import ConversationService

USER_ID = "user-1"
SESSION_ID = "session-1"
QUERY = "How many collections are in Milvus?"
ANSWER = "There are 12 collections."
FILENAME = "photo.png"
IMAGE_BYTES = b"image-bytes"
OBJECT_KEY = f"{APP_NAME}/{USER_ID}/{SESSION_ID}/{FILENAME}/0"
EVENT_TIMESTAMP = 1_700_000_000.0
FIXED_DATETIME = datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)


async def _async_iter(items):
    for item in items:
        yield item


def _final_event(mocker, text=ANSWER, timestamp=EVENT_TIMESTAMP):
    event = mocker.MagicMock()
    event.is_final_response.return_value = True
    event.timestamp = timestamp
    event.content.parts = [mocker.MagicMock(text=text)]
    return event


def _escalated_event(mocker, error_message="quota exceeded"):
    event = mocker.MagicMock()
    event.is_final_response.return_value = True
    event.timestamp = EVENT_TIMESTAMP
    event.content = None
    event.actions.escalate = True
    event.error_message = error_message
    return event


def _intermediate_event(mocker):
    event = mocker.MagicMock()
    event.is_final_response.return_value = False
    return event


@pytest.fixture
def sessions(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def artifacts(mocker):
    artifacts = mocker.AsyncMock()
    artifacts.save_artifact.return_value = 0
    artifacts.get_object_key = mocker.MagicMock(return_value=OBJECT_KEY)
    return artifacts


@pytest.fixture
def storage(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def mock_runner(mocker):
    runner = mocker.MagicMock()
    runner.run_async = mocker.MagicMock(return_value=_async_iter([]))
    mocker.patch(
        "data_agent.services.conversation_service.Runner", return_value=runner
    )
    return runner


@pytest.fixture
def mock_types(mocker):
    return mocker.patch("data_agent.services.conversation_service.types")


@pytest.fixture
def mock_event(mocker):
    return mocker.patch("data_agent.services.conversation_service.Event")


@pytest.fixture
def mock_event_actions(mocker):
    return mocker.patch("data_agent.services.conversation_service.EventActions")


@pytest.fixture
def mock_convert(mocker):
    return mocker.patch(
        "data_agent.services.conversation_service.convert_unix_to_datetime",
        return_value=FIXED_DATETIME,
    )


@pytest.fixture
def service(sessions, artifacts, storage, mock_runner):
    return ConversationService(sessions, artifacts, storage)


@pytest.fixture
def request_body():
    return RunAgentRequest(query=QUERY)


@pytest.fixture
def image_file(mocker):
    upload = mocker.MagicMock()
    upload.read = mocker.AsyncMock(return_value=IMAGE_BYTES)
    upload.filename = FILENAME
    upload.content_type = "image/png"
    return upload


class TestInit:

    def test_builds_a_runner_for_the_agent_app(
        self, mocker, sessions, artifacts, storage
    ):
        from data_agent.agents import agent_app

        mock_runner_class = mocker.patch(
            "data_agent.services.conversation_service.Runner"
        )

        service = ConversationService(sessions, artifacts, storage)

        mock_runner_class.assert_called_once_with(
            app=agent_app,
            app_name=APP_NAME,
            session_service=sessions,
            artifact_service=artifacts,
        )
        assert service._runner is mock_runner_class.return_value

    def test_keeps_its_collaborators(self, service, sessions, artifacts, storage):
        assert service._sessions is sessions
        assert service._artifacts is artifacts
        assert service._storage is storage
        assert service._app_name == APP_NAME


class TestRunWithoutImage:
    pytestmark = pytest.mark.asyncio

    async def test_returns_the_final_response(
        self, mocker, service, mock_runner, mock_types, mock_convert, request_body
    ):
        mock_runner.run_async.return_value = _async_iter([_final_event(mocker)])

        result = await service.run(USER_ID, SESSION_ID, request_body)

        assert isinstance(result, RunAgentResponse)
        assert result.response == ANSWER
        assert result.timestamp == FIXED_DATETIME

    async def test_sends_only_the_query_to_the_runner(
        self, mocker, service, mock_runner, mock_types, mock_convert, request_body
    ):
        mock_runner.run_async.return_value = _async_iter([_final_event(mocker)])

        await service.run(USER_ID, SESSION_ID, request_body)

        mock_types.Part.assert_called_once_with(text=QUERY)
        mock_types.Content.assert_called_once_with(
            role="user", parts=[mock_types.Part.return_value]
        )
        mock_runner.run_async.assert_called_once_with(
            user_id=USER_ID,
            session_id=SESSION_ID,
            new_message=mock_types.Content.return_value,
        )

    async def test_does_not_touch_artifact_storage(
        self, mocker, service, artifacts, sessions, mock_runner, mock_types,
        mock_convert, request_body
    ):
        mock_runner.run_async.return_value = _async_iter([_final_event(mocker)])

        await service.run(USER_ID, SESSION_ID, request_body)

        artifacts.save_artifact.assert_not_awaited()
        sessions.get_session.assert_not_awaited()
        sessions.append_event.assert_not_awaited()

    async def test_converts_the_event_timestamp(
        self, mocker, service, mock_runner, mock_types, mock_convert, request_body
    ):
        mock_runner.run_async.return_value = _async_iter([_final_event(mocker)])

        await service.run(USER_ID, SESSION_ID, request_body)

        mock_convert.assert_called_once_with(EVENT_TIMESTAMP)

    async def test_ignores_intermediate_events(
        self, mocker, service, mock_runner, mock_types, mock_convert, request_body
    ):
        mock_runner.run_async.return_value = _async_iter([
            _intermediate_event(mocker),
            _final_event(mocker),
        ])

        result = await service.run(USER_ID, SESSION_ID, request_body)

        assert result.response == ANSWER

    async def test_stops_at_the_first_final_response(
        self, mocker, service, mock_runner, mock_types, mock_convert, request_body
    ):
        second = _final_event(mocker, text="second")
        mock_runner.run_async.return_value = _async_iter([
            _final_event(mocker, text="first"),
            second,
        ])

        result = await service.run(USER_ID, SESSION_ID, request_body)

        assert result.response == "first"
        second.is_final_response.assert_not_called()

    async def test_uses_the_last_part_of_the_response(
        self, mocker, service, mock_runner, mock_types, mock_convert, request_body
    ):
        event = _final_event(mocker)
        event.content.parts = [
            mocker.MagicMock(text="first"),
            mocker.MagicMock(text="last"),
        ]
        mock_runner.run_async.return_value = _async_iter([event])

        result = await service.run(USER_ID, SESSION_ID, request_body)

        assert result.response == "last"

    async def test_reports_escalation(
        self, mocker, service, mock_runner, mock_types, mock_convert, request_body
    ):
        mock_runner.run_async.return_value = _async_iter([_escalated_event(mocker)])

        result = await service.run(USER_ID, SESSION_ID, request_body)

        assert result.response == "Agent escalated: quota exceeded"

    async def test_reports_escalation_without_a_message(
        self, mocker, service, mock_runner, mock_types, mock_convert, request_body
    ):
        mock_runner.run_async.return_value = _async_iter([
            _escalated_event(mocker, error_message=None)
        ])

        result = await service.run(USER_ID, SESSION_ID, request_body)

        assert result.response == "Agent escalated: No specific message."

    async def test_falls_back_when_the_agent_returns_nothing(
        self, service, mock_runner, mock_types, mock_convert, request_body
    ):
        mock_runner.run_async.return_value = _async_iter([])

        result = await service.run(USER_ID, SESSION_ID, request_body)

        assert result.response == "No response received."
        mock_convert.assert_called_once_with(None)

    async def test_raises_when_the_agent_returns_nothing_and_no_timestamp_exists(
        self, service, mock_runner, mock_types, request_body
    ):
        mock_runner.run_async.return_value = _async_iter([])

        with pytest.raises(TypeError):
            await service.run(USER_ID, SESSION_ID, request_body)

    async def test_propagates_runner_errors(
        self, service, mock_runner, mock_types, mock_convert, request_body
    ):
        mock_runner.run_async.side_effect = RuntimeError("model unavailable")

        with pytest.raises(RuntimeError, match="model unavailable"):
            await service.run(USER_ID, SESSION_ID, request_body)

    async def test_logs_the_failure(
        self, mocker, service, mock_runner, mock_types, request_body
    ):
        mock_logger = mocker.patch("data_agent.services.conversation_service.logger")
        mock_runner.run_async.side_effect = RuntimeError("model unavailable")

        with pytest.raises(RuntimeError):
            await service.run(USER_ID, SESSION_ID, request_body)

        mock_logger.exception.assert_called_once()


class TestRunWithImage:
    pytestmark = pytest.mark.asyncio

    @pytest.fixture(autouse=True)
    def final_event(self, mocker, mock_runner):
        mock_runner.run_async.return_value = _async_iter([_final_event(mocker)])

    async def test_reads_the_uploaded_file(
        self, service, image_file, mock_types, mock_event, mock_event_actions,
        mock_convert, request_body
    ):
        await service.run(USER_ID, SESSION_ID, request_body, image_file)

        image_file.read.assert_awaited_once_with()

    async def test_saves_the_image_as_an_artifact(
        self, service, artifacts, image_file, mock_types, mock_event,
        mock_event_actions, mock_convert, request_body
    ):
        await service.run(USER_ID, SESSION_ID, request_body, image_file)

        mock_types.Part.from_bytes.assert_called_with(
            data=IMAGE_BYTES, mime_type="image/png"
        )
        artifacts.save_artifact.assert_awaited_once_with(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=SESSION_ID,
            filename=FILENAME,
            artifact=mock_types.Part.from_bytes.return_value,
        )

    async def test_defaults_the_content_type(
        self, service, artifacts, image_file, mock_types, mock_event,
        mock_event_actions, mock_convert, request_body
    ):
        image_file.content_type = None

        await service.run(USER_ID, SESSION_ID, request_body, image_file)

        mock_types.Part.from_bytes.assert_called_with(
            data=IMAGE_BYTES, mime_type="image/jpeg"
        )

    async def test_resolves_the_object_key_for_the_saved_version(
        self, service, artifacts, image_file, mock_types, mock_event,
        mock_event_actions, mock_convert, request_body
    ):
        artifacts.save_artifact.return_value = 3

        await service.run(USER_ID, SESSION_ID, request_body, image_file)

        artifacts.get_object_key.assert_called_once_with(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=SESSION_ID,
            filename=FILENAME,
            version=3,
        )

    async def test_records_the_pending_image_in_session_state(
        self, mocker, service, sessions, image_file, mock_types, mock_event,
        mock_event_actions, mock_convert, request_body
    ):
        session = mocker.MagicMock()
        sessions.get_session.return_value = session

        await service.run(USER_ID, SESSION_ID, request_body, image_file)

        sessions.get_session.assert_awaited_once_with(
            app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
        )
        mock_event_actions.assert_called_once_with(state_delta={"pending_image": {
            "key": OBJECT_KEY, "filename": FILENAME, "content_type": "image/png"
        }})
        mock_event.assert_called_once_with(
            author="system", actions=mock_event_actions.return_value
        )
        sessions.append_event.assert_awaited_once_with(
            session, mock_event.return_value
        )

    async def test_sends_the_image_before_the_query(
        self, service, image_file, mock_types, mock_event, mock_event_actions,
        mock_convert, request_body
    ):
        await service.run(USER_ID, SESSION_ID, request_body, image_file)

        mock_types.Content.assert_called_once_with(role="user", parts=[
            mock_types.Part.from_bytes.return_value,
            mock_types.Part.return_value,
        ])

    async def test_returns_the_agent_response(
        self, service, image_file, mock_types, mock_event, mock_event_actions,
        mock_convert, request_body
    ):
        result = await service.run(USER_ID, SESSION_ID, request_body, image_file)

        assert result.response == ANSWER
        assert result.timestamp == FIXED_DATETIME

    async def test_propagates_upload_read_errors(
        self, service, artifacts, image_file, mock_types, mock_convert, request_body
    ):
        image_file.read.side_effect = RuntimeError("stream closed")

        with pytest.raises(RuntimeError, match="stream closed"):
            await service.run(USER_ID, SESSION_ID, request_body, image_file)

        artifacts.save_artifact.assert_not_awaited()

    async def test_propagates_artifact_errors(
        self, service, sessions, artifacts, image_file, mock_types, mock_convert,
        request_body
    ):
        artifacts.save_artifact.side_effect = RuntimeError("storage down")

        with pytest.raises(RuntimeError, match="storage down"):
            await service.run(USER_ID, SESSION_ID, request_body, image_file)

        sessions.append_event.assert_not_awaited()
