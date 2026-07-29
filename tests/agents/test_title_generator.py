import pytest

from common.constants import SYSTEM_APP_NAME, SYSTEM_MODEL_NAME_OR_ID
from data_agent.agents import title_generator
from data_agent.agents.prompts.title_generator import (
    SYSTEM_AGENT_INSTRUCTION,
    SYSTEM_AGENT_NAME,
)


@pytest.fixture
def mock_build_model(mocker):
    return mocker.patch("fabrix.adk.models.build_model", return_value="system-model")


@pytest.fixture
def mock_create_app(mocker):
    return mocker.patch("fabrix.adk.factory.create_fabrix_app")


@pytest.fixture
def mock_agent(mocker):
    return mocker.patch("google.adk.agents.llm_agent.Agent")


@pytest.fixture
def module(reload_module, mock_build_model, mock_create_app, mock_agent):
    return reload_module(title_generator)


class TestSystemAgent:

    def test_builds_the_system_model(self, module, mock_build_model):
        mock_build_model.assert_called_once_with(SYSTEM_MODEL_NAME_OR_ID)
        assert module.system_model is mock_build_model.return_value

    def test_builds_the_agent_from_its_prompt(
        self, module, mock_agent, mock_build_model
    ):
        mock_agent.assert_called_once_with(
            model=mock_build_model.return_value,
            name=SYSTEM_AGENT_NAME,
            instruction=SYSTEM_AGENT_INSTRUCTION,
        )
        assert module.system_agent is mock_agent.return_value

    def test_has_no_tools(self, module, mock_agent):
        assert "tools" not in mock_agent.call_args.kwargs

    def test_wraps_the_agent_in_a_fabrix_app(self, module, mock_create_app, mock_agent):
        mock_create_app.assert_called_once_with(
            mock_agent.return_value, app_name=SYSTEM_APP_NAME
        )
        assert module.system_app is mock_create_app.return_value


class TestLiveModule:

    def test_the_package_exports_the_app(self):
        import data_agent.agents

        assert hasattr(data_agent.agents, "system_app")

    def test_the_agent_is_named_after_its_prompt(self):
        assert title_generator.system_agent.name == SYSTEM_AGENT_NAME

    def test_uses_a_different_model_from_the_data_agents(self):
        from common.constants import MODEL_NAME_OR_ID

        assert SYSTEM_MODEL_NAME_OR_ID != MODEL_NAME_OR_ID
