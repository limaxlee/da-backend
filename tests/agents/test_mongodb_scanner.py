import pytest

from common.constants import MODEL_NAME_OR_ID
from data_agent.agents import mongodb_scanner
from data_agent.agents.prompts.mongodb_scanner import (
    MONGODB_AGENT_INSTRUCTION,
    MONGODB_AGENT_NAME,
)
from data_agent.agents.toolsets import CachedMcpToolset

HOST = "mongodb-mcp.internal"
PORT = 8446


@pytest.fixture
def mock_build_model(mocker):
    return mocker.patch(
        "fabrix.adk.models.build_model", return_value="mongodb-model"
    )


@pytest.fixture
def mock_agent(mocker):
    return mocker.patch("google.adk.agents.llm_agent.Agent")


@pytest.fixture
def mock_toolset(mocker):
    return mocker.patch("data_agent.agents.toolsets.CachedMcpToolset")


@pytest.fixture
def mock_connection_params(mocker):
    return mocker.patch(
        "google.adk.tools.mcp_tool.mcp_session_manager.StreamableHTTPConnectionParams"
    )


@pytest.fixture
def mock_settings(mocker):
    settings = mocker.patch("common.config.SETTINGS")
    settings.mongodb_mcp.host = HOST
    settings.mongodb_mcp.port = PORT
    return settings


@pytest.fixture
def module(
    reload_module,
    mock_build_model,
    mock_agent,
    mock_toolset,
    mock_connection_params,
    mock_settings,
):
    return reload_module(mongodb_scanner)


class TestMongodbAgent:

    def test_builds_the_configured_model(self, module, mock_build_model):
        mock_build_model.assert_called_once_with(MODEL_NAME_OR_ID)
        assert module.mongodb_model is mock_build_model.return_value

    def test_connects_to_the_configured_mcp_server(
        self, module, mock_connection_params
    ):
        mock_connection_params.assert_called_once_with(
            url=f"http://{HOST}:{PORT}/mcp"
        )

    def test_uses_the_caching_toolset(self, module, mock_toolset,
                                      mock_connection_params):
        mock_toolset.assert_called_once_with(
            connection_params=mock_connection_params.return_value
        )

    def test_builds_the_agent_from_its_prompt(self, module, mock_agent,
                                              mock_build_model, mock_toolset):
        mock_agent.assert_called_once_with(
            model=mock_build_model.return_value,
            name=MONGODB_AGENT_NAME,
            instruction=MONGODB_AGENT_INSTRUCTION,
            tools=[mock_toolset.return_value],
        )
        assert module.mongodb_agent is mock_agent.return_value

    def test_has_no_tool_callback(self, module, mock_agent):
        assert "before_tool_callback" not in mock_agent.call_args.kwargs

    def test_the_live_agent_uses_a_cached_toolset(self):
        assert isinstance(mongodb_scanner.mongodb_agent.tools[0], CachedMcpToolset)
