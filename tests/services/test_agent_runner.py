from types import SimpleNamespace

import pytest

from common.constants import APP_NAME
from data_agent.agents import agent_app
from data_agent.schemas import RunAgentRequest
from data_agent.services.agent_runner import AgentRunner
from data_agent.utils import convert_unix_to_datetime

TIMESTAMP = 1_700_000_000.0


def _final_event(text="final answer"):
    return SimpleNamespace(
        author="root_agent",
        timestamp=TIMESTAMP,
        is_final_response=lambda: True,
        content=SimpleNamespace(parts=[SimpleNamespace(text=text)]),
        actions=None,
        error_message=None,
    )


class TestAgentRunner:
    @pytest.mark.asyncio
    async def test_run(self, mocker):
        runner_cls = mocker.patch("data_agent.services.agent_runner.Runner")
        session_service = mocker.Mock()
        artifact_service = mocker.Mock()
        agent_runner = AgentRunner(session_service=session_service, artifact_service=artifact_service)
        runner_cls.assert_called_once_with(
            app=agent_app,
            app_name=APP_NAME,
            session_service=session_service,
            artifact_service=artifact_service,
        )

        async def _events(**kwargs):
            yield _final_event()

        run_async = mocker.Mock(side_effect=_events)
        runner_cls.return_value.run_async = run_async

        response = await agent_runner.run(
            user_id="u1", session_id="s1", request=RunAgentRequest(query="hello"), image_file=None
        )

        assert response.response == "final answer"
        assert response.timestamp == convert_unix_to_datetime(TIMESTAMP)
        kwargs = run_async.call_args.kwargs
        assert kwargs["user_id"] == "u1"
        assert kwargs["session_id"] == "s1"
        assert kwargs["new_message"].role == "user"
        assert kwargs["new_message"].parts[-1].text == "hello"

        run_async.side_effect = RuntimeError("model down")
        with pytest.raises(RuntimeError):
            await agent_runner.run(user_id="u1", session_id="s1", request=RunAgentRequest(query="hello"))
