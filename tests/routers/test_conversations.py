from datetime import datetime, timezone

import pytest
from fastapi import status
from starlette.datastructures import UploadFile

from data_agent.schemas import RunAgentRequest, RunAgentResponse

USER_ID = "user-1"
SESSION_ID = "session-1"
QUERY = "How many collections are in Milvus?"
ANSWER = "There are 12 collections."
TIMESTAMP = datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)
FILENAME = "photo.png"
IMAGE_BYTES = b"image-bytes"

RUN_URL = f"/apps/users/{USER_ID}/sessions/{SESSION_ID}/run"


@pytest.fixture
def conversation_service(mocker):
    service = mocker.patch(
        "data_agent.routers.conversations.conversation_service",
        new_callable=mocker.AsyncMock,
    )
    service.run.return_value = RunAgentResponse(
        response=ANSWER, timestamp=TIMESTAMP
    )
    return service


class TestRun:

    def test_returns_the_agent_response(self, client, conversation_service):
        response = client.post(RUN_URL, params={"query": QUERY})

        assert response.status_code == status.HTTP_200_OK
        assert response.json() == {
            "response": ANSWER,
            "timestamp": "2023-11-14T22:13:20Z",
            "files": [],
        }

    def test_accepts_the_query_as_a_query_parameter(self, client, conversation_service):
        client.post(RUN_URL, params={"query": QUERY})

        conversation_service.run.assert_awaited_once()
        kwargs = conversation_service.run.await_args.kwargs
        assert kwargs["user_id"] == USER_ID
        assert kwargs["session_id"] == SESSION_ID
        assert isinstance(kwargs["request"], RunAgentRequest)
        assert kwargs["request"].query == QUERY

    def test_passes_no_image_when_none_is_uploaded(
        self, client, conversation_service
    ):
        client.post(RUN_URL, params={"query": QUERY})

        assert conversation_service.run.await_args.kwargs["image_file"] is None

    def test_forwards_the_uploaded_image(self, client, conversation_service):
        response = client.post(
            RUN_URL,
            params={"query": QUERY},
            files={"image_file": (FILENAME, IMAGE_BYTES, "image/png")},
        )

        assert response.status_code == status.HTTP_200_OK
        image_file = conversation_service.run.await_args.kwargs["image_file"]
        assert isinstance(image_file, UploadFile)
        assert image_file.filename == FILENAME
        assert image_file.content_type == "image/png"

    def test_the_uploaded_image_is_readable_by_the_service(
        self, mocker, client, conversation_service
    ):
        read_bytes = {}

        async def capture(*, user_id, session_id, request, image_file):
            read_bytes["data"] = await image_file.read()
            return RunAgentResponse(response=ANSWER, timestamp=TIMESTAMP)

        conversation_service.run.side_effect = capture

        client.post(
            RUN_URL,
            params={"query": QUERY},
            files={"image_file": (FILENAME, IMAGE_BYTES, "image/png")},
        )

        assert read_bytes["data"] == IMAGE_BYTES

    def test_requires_the_query(self, client, conversation_service):
        response = client.post(RUN_URL)

        assert response.status_code == 422
        conversation_service.run.assert_not_awaited()

    def test_ignores_a_json_body(self, client, conversation_service):
        response = client.post(RUN_URL, json={"query": QUERY})

        assert response.status_code == 422
        conversation_service.run.assert_not_awaited()

    def test_accepts_an_empty_query(self, client, conversation_service):
        response = client.post(RUN_URL, params={"query": ""})

        assert response.status_code == status.HTTP_200_OK
        assert conversation_service.run.await_args.kwargs["request"].query == ""

    def test_maps_failures_to_500(self, client, conversation_service):
        conversation_service.run.side_effect = RuntimeError("model unavailable")

        response = client.post(RUN_URL, params={"query": QUERY})

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
        assert response.json() == {"detail": "model unavailable"}

    def test_maps_value_errors_to_500(self, client, conversation_service):
        conversation_service.run.side_effect = ValueError("does not have session")

        response = client.post(RUN_URL, params={"query": QUERY})

        assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    def test_logs_the_start_and_end_of_a_successful_run(
        self, mocker, client, conversation_service
    ):
        mock_logger = mocker.patch("data_agent.routers.conversations.logger")

        client.post(RUN_URL, params={"query": QUERY})

        messages = [call.args[0] for call in mock_logger.info.call_args_list]
        assert any("/run START" in message for message in messages)
        assert any("/run END" in message for message in messages)

    def test_logs_a_failed_run(self, mocker, client, conversation_service):
        mock_logger = mocker.patch("data_agent.routers.conversations.logger")
        conversation_service.run.side_effect = RuntimeError("model unavailable")

        client.post(RUN_URL, params={"query": QUERY})

        messages = [call.args[0] for call in mock_logger.info.call_args_list]
        assert any("/run FAILED" in message for message in messages)
        assert not any("/run END" in message for message in messages)


class TestRouting:

    def test_is_mounted_under_the_apps_prefix(self, client, conversation_service):
        response = client.post(
            f"/users/{USER_ID}/sessions/{SESSION_ID}/run", params={"query": QUERY}
        )

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_rejects_other_methods(self, client, conversation_service):
        assert client.get(RUN_URL).status_code == status.HTTP_405_METHOD_NOT_ALLOWED
