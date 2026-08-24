import asyncio
from types import SimpleNamespace

import pytest

from common.constants import APP_NAME
from data_agent.agents import agent_app
from data_agent.schemas import RunAgentRequest
from data_agent.services.agent_runner import AgentRunner
from data_agent.services.session_guard import SessionGuard
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


@pytest.fixture
def session_guard():
    return SessionGuard()


@pytest.fixture
def db_session_service(mocker):
    return mocker.Mock(ensure_session_title=mocker.AsyncMock())


@pytest.fixture
def agent_runner(mocker, session_guard, db_session_service):
    runner_cls = mocker.patch("data_agent.services.agent_runner.Runner")
    session_service = mocker.Mock()
    artifact_service = mocker.Mock()
    runner = AgentRunner(
        session_service=session_service,
        artifact_service=artifact_service,
        db_session_service=db_session_service,
        session_guard=session_guard,
    )
    runner_cls.assert_called_once_with(
        app=agent_app,
        app_name=APP_NAME,
        session_service=session_service,
        artifact_service=artifact_service,
    )
    return runner


def _yields_final_event(mocker):
    async def _events(**kwargs):
        yield _final_event()

    return mocker.Mock(side_effect=_events)


class TestAgentRunner:
    @pytest.mark.asyncio
    async def test_run(self, mocker, agent_runner):
        run_async = _yields_final_event(mocker)
        agent_runner._runner.run_async = run_async

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

    @pytest.mark.asyncio
    async def test_run_holds_the_session_guard_and_releases_it(self, mocker, agent_runner, session_guard):
        held = []

        async def _events(**kwargs):
            held.append(session_guard.is_busy("s1"))
            yield _final_event()

        agent_runner._runner.run_async = mocker.Mock(side_effect=_events)

        await agent_runner.run(user_id="u1", session_id="s1", request=RunAgentRequest(query="hello"))

        assert held == [True]
        assert session_guard.is_busy("s1") is False

    @pytest.mark.asyncio
    async def test_run_releases_the_session_guard_on_failure(self, mocker, agent_runner, session_guard):
        agent_runner._runner.run_async = mocker.Mock(side_effect=RuntimeError("model down"))

        with pytest.raises(RuntimeError):
            await agent_runner.run(user_id="u1", session_id="s1", request=RunAgentRequest(query="hello"))

        assert session_guard.is_busy("s1") is False

    @pytest.mark.asyncio
    async def test_run_titles_the_session_afterwards(self, mocker, agent_runner, db_session_service, session_guard):
        agent_runner._runner.run_async = _yields_final_event(mocker)

        await agent_runner.run(user_id="u1", session_id="s1", request=RunAgentRequest(query="hello"))

        # The titling task is scheduled, not awaited, so the run does not pay for it.
        assert agent_runner._background_tasks
        await asyncio.gather(*agent_runner._background_tasks)

        db_session_service.ensure_session_title.assert_awaited_once_with("u1", "s1")
        assert agent_runner._background_tasks == set()

    @pytest.mark.asyncio
    async def test_run_does_not_title_a_failed_run(self, mocker, agent_runner, db_session_service):
        agent_runner._runner.run_async = mocker.Mock(side_effect=RuntimeError("model down"))

        with pytest.raises(RuntimeError):
            await agent_runner.run(user_id="u1", session_id="s1", request=RunAgentRequest(query="hello"))

        db_session_service.ensure_session_title.assert_not_awaited()
