from types import SimpleNamespace

import pytest

from common.constants import SYSTEM_APP_NAME
from data_agent.services.system_runner import SystemRunner


def _final_event(text):
    return SimpleNamespace(
        is_final_response=lambda: True,
        content=SimpleNamespace(parts=[SimpleNamespace(text=text)]),
    )


class TestSystemRunner:
    @pytest.mark.asyncio
    async def test_create_session_title(self, mocker):
        runner_cls = mocker.patch("data_agent.services.system_runner.Runner")
        session_service_cls = mocker.patch("data_agent.services.system_runner.InMemorySessionService")
        session_service = session_service_cls.return_value
        session_service.create_session = mocker.AsyncMock(return_value=SimpleNamespace(id="tmp-session"))
        session_service.delete_session = mocker.AsyncMock()

        async def _events(**kwargs):
            yield _final_event("Bucket Inventory")

        run_async = mocker.Mock(side_effect=_events)
        runner_cls.return_value.run_async = run_async
        system_runner = SystemRunner()

        title = await system_runner.create_session_title(
            user_id="u1", session_id="s1", user_message="what is in the bucket?"
        )

        assert title == "Bucket Inventory"
        session_service.create_session.assert_awaited_once_with(app_name=SYSTEM_APP_NAME, user_id="u1")
        session_service.delete_session.assert_awaited_once_with(
            app_name=SYSTEM_APP_NAME, user_id="u1", session_id="tmp-session"
        )
        kwargs = run_async.call_args.kwargs
        assert kwargs["user_id"] == "u1"
        assert kwargs["session_id"] == "tmp-session"
        assert kwargs["new_message"].parts[-1].text == "what is in the bucket?"

        async def _empty_events(**kwargs):
            yield _final_event("")

        run_async.side_effect = _empty_events
        with pytest.raises(ValueError):
            await system_runner.create_session_title(user_id="u1", session_id="s1", user_message="hi")
