import data_agent.agents.system_agent

from common.constants import SYSTEM_APP_NAME, SYSTEM_MODEL_NAME_OR_ID
from data_agent.agents.prompts.system_agent import SYSTEM_AGENT_NAME, SYSTEM_AGENT_INSTRUCTION


def test_system_agent(mocker, reload_module):
    build_model = mocker.patch("fabrix.adk.models.build_model")
    mocker.patch("fabrix.adk.runtime.create_runtime_app")
    agent_cls = mocker.patch("google.adk.agents.llm_agent.Agent")

    module = reload_module(data_agent.agents.system_agent)

    build_model.assert_called_once_with(SYSTEM_MODEL_NAME_OR_ID)
    agent_cls.assert_called_once_with(
        model=build_model.return_value,
        name=SYSTEM_AGENT_NAME,
        instruction=SYSTEM_AGENT_INSTRUCTION,
    )
    assert module.system_agent is agent_cls.return_value


def test_system_app(mocker, reload_module):
    mocker.patch("fabrix.adk.models.build_model")
    agent_cls = mocker.patch("google.adk.agents.llm_agent.Agent")
    create_runtime_app = mocker.patch("fabrix.adk.runtime.create_runtime_app")

    module = reload_module(data_agent.agents.system_agent)

    create_runtime_app.assert_called_once_with(agent_cls.return_value, app_name=SYSTEM_APP_NAME)
    assert module.system_app is create_runtime_app.return_value
