import data_agent.agents.milvus_scanner
import data_agent.agents.mongodb_scanner
import data_agent.agents.root_orchestrator

from common.constants import APP_NAME, MODEL_NAME_OR_ID
from data_agent.agents.prompts.root_orchestrator import (
    ROOT_AGENT_NAME, ROOT_AGENT_DESCRIPTION, ROOT_AGENT_INSTRUCTION
)


def test_root_agent(mocker, reload_module):
    build_model = mocker.patch("fabrix.adk.models.build_model")
    mocker.patch("fabrix.adk.runtime.create_runtime_app")
    agent_cls = mocker.patch("google.adk.agents.llm_agent.Agent")
    agent_tool_cls = mocker.patch("google.adk.tools.AgentTool")

    module = reload_module(data_agent.agents.root_orchestrator)

    build_model.assert_called_once_with(MODEL_NAME_OR_ID)
    agent_tool_cls.assert_has_calls([
        mocker.call(agent=data_agent.agents.milvus_scanner.milvus_agent),
        mocker.call(agent=data_agent.agents.mongodb_scanner.mongodb_agent),
    ])
    agent_cls.assert_called_once_with(
        model=build_model.return_value,
        name=ROOT_AGENT_NAME,
        description=ROOT_AGENT_DESCRIPTION,
        instruction=ROOT_AGENT_INSTRUCTION,
        tools=[agent_tool_cls.return_value, agent_tool_cls.return_value],
    )
    assert module.root_agent is agent_cls.return_value


def test_agent_app(mocker, reload_module):
    mocker.patch("fabrix.adk.models.build_model")
    mocker.patch("google.adk.tools.AgentTool")
    agent_cls = mocker.patch("google.adk.agents.llm_agent.Agent")
    create_runtime_app = mocker.patch("fabrix.adk.runtime.create_runtime_app")

    module = reload_module(data_agent.agents.root_orchestrator)

    create_runtime_app.assert_called_once_with(agent_cls.return_value, app_name=APP_NAME)
    assert module.agent_app is create_runtime_app.return_value
