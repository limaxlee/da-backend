from datetime import datetime, timezone

from data_agent.schemas import RunAgentResponse


def test_run(client, agent_runner):
    agent_runner.run.return_value = RunAgentResponse(
        response="final answer", timestamp=datetime(2026, 8, 23, tzinfo=timezone.utc)
    )

    response = client.post("/apps/users/user-1/sessions/s1/run", params={"query": "hello"})

    assert response.status_code == 200
    assert response.json()["response"] == "final answer"
    kwargs = agent_runner.run.await_args.kwargs
    assert kwargs["user_id"] == "user-1"
    assert kwargs["session_id"] == "s1"
    assert kwargs["request"].query == "hello"

    agent_runner.run.side_effect = RuntimeError("model down")
    failed = client.post("/apps/users/user-1/sessions/s1/run", params={"query": "hello"})
    assert failed.status_code == 500
    assert failed.json()["detail"] == "model down"
