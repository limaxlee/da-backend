import pytest

from common.constants import APP_NAME, MODEL_NAME_OR_ID
from data_agent.agents import root_orchestrator
from data_agent.agents.prompts.root_orchestrator import (
    ROOT_AGENT_DESCRIPTION,
    ROOT_AGENT_INSTRUCTION,
    ROOT_AGENT_NAME,
)


@pytest.fixture
def mock_build_model(mocker):
    return mocker.patch("fabrix.adk.models.build_model", return_value="root-model")


@pytest.fixture
def mock_create_app(mocker):
    return mocker.patch("fabrix.adk.factory.create_fabrix_app")


@pytest.fixture
def mock_agent(mocker):
    return mocker.patch("google.adk.agents.llm_agent.Agent")


@pytest.fixture
def mock_agent_tool(mocker):
    return mocker.patch("google.adk.tools.AgentTool")


@pytest.fixture
def milvus_agent(mocker):
    agent = mocker.MagicMock(name="milvus-agent")
    mocker.patch("data_agent.agents.milvus_scanner.milvus_agent", new=agent)
    return agent


@pytest.fixture
def mongodb_agent(mocker):
    agent = mocker.MagicMock(name="mongodb-agent")
    mocker.patch("data_agent.agents.mongodb_scanner.mongodb_agent", new=agent)
    return agent


@pytest.fixture
def module(
    reload_module,
    mock_build_model,
    mock_create_app,
    mock_agent,
    mock_agent_tool,
    milvus_agent,
    mongodb_agent,
):
    return reload_module(root_orchestrator)


class TestRootAgent:

    def test_builds_the_configured_model(self, module, mock_build_model):
        mock_build_model.assert_called_once_with(MODEL_NAME_OR_ID)
        assert module.root_model is mock_build_model.return_value

    def test_builds_the_agent_from_its_prompt(
        self, module, mock_agent, mock_build_model, mock_agent_tool
    ):
        mock_agent.assert_called_once_with(
            model=mock_build_model.return_value,
            name=ROOT_AGENT_NAME,
            description=ROOT_AGENT_DESCRIPTION,
            instruction=ROOT_AGENT_INSTRUCTION,
            tools=[mock_agent_tool.return_value, mock_agent_tool.return_value],
        )
        assert module.root_agent is mock_agent.return_value

    def test_exposes_both_scanners_as_tools(
        self, module, mock_agent_tool, milvus_agent, mongodb_agent
    ):
        assert mock_agent_tool.call_count == 2
        assert [call.kwargs["agent"] for call in mock_agent_tool.call_args_list] == [
            milvus_agent,
            mongodb_agent,
        ]

    def test_wraps_the_agent_in_a_fabrix_app(self, module, mock_create_app, mock_agent):
        mock_create_app.assert_called_once_with(
            mock_agent.return_value, app_name=APP_NAME
        )
        assert module.agent_app is mock_create_app.return_value


class TestLiveModule:

    def test_the_package_exports_the_app(self):
        import data_agent.agents

        assert hasattr(data_agent.agents, "agent_app")

    def test_the_agent_is_named_after_its_prompt(self):
        assert root_orchestrator.root_agent.name == ROOT_AGENT_NAME

    def test_the_agent_carries_two_tools(self):
        assert len(root_orchestrator.root_agent.tools) == 2
