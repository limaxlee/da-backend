import pytest

from common.constants import MODEL_NAME_OR_ID
from data_agent.agents import milvus_scanner
from data_agent.agents.callbacks import inject_pending_image
from data_agent.agents.prompts.milvus_scanner import (
    MILVUS_AGENT_INSTRUCTION,
    MILVUS_AGENT_NAME,
)

HOST = "milvus-mcp.internal"
PORT = 8443


@pytest.fixture
def mock_build_model(mocker):
    return mocker.patch(
        "fabrix.adk.models.build_model", return_value="milvus-model"
    )


@pytest.fixture
def mock_agent(mocker):
    return mocker.patch("google.adk.agents.llm_agent.Agent")


@pytest.fixture
def mock_toolset(mocker):
    return mocker.patch("google.adk.tools.mcp_tool.McpToolset")


@pytest.fixture
def mock_connection_params(mocker):
    return mocker.patch(
        "google.adk.tools.mcp_tool.mcp_session_manager.StreamableHTTPConnectionParams"
    )


@pytest.fixture
def mock_settings(mocker):
    settings = mocker.patch("common.config.SETTINGS")
    settings.milvus_mcp.host = HOST
    settings.milvus_mcp.port = PORT
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
    return reload_module(milvus_scanner)


class TestMilvusAgent:

    def test_builds_the_configured_model(self, module, mock_build_model):
        mock_build_model.assert_called_once_with(MODEL_NAME_OR_ID)
        assert module.milvus_model is mock_build_model.return_value

    def test_connects_to_the_configured_mcp_server(
        self, module, mock_connection_params
    ):
        mock_connection_params.assert_called_once_with(
            url=f"http://{HOST}:{PORT}/mcp"
        )

    def test_registers_a_single_mcp_toolset(self, module, mock_toolset,
                                            mock_connection_params):
        mock_toolset.assert_called_once_with(
            connection_params=mock_connection_params.return_value
        )

    def test_builds_the_agent_from_its_prompt(self, module, mock_agent,
                                              mock_build_model, mock_toolset):
        mock_agent.assert_called_once_with(
            model=mock_build_model.return_value,
            name=MILVUS_AGENT_NAME,
            instruction=MILVUS_AGENT_INSTRUCTION,
            before_tool_callback=inject_pending_image,
            tools=[mock_toolset.return_value],
        )
        assert module.milvus_agent is mock_agent.return_value

    def test_injects_the_pending_image_before_each_tool_call(
        self, module, mock_agent
    ):
        assert mock_agent.call_args.kwargs["before_tool_callback"] is (
            inject_pending_image
        )

    def test_does_not_use_the_caching_toolset(self):
        from data_agent.agents.toolsets import CachedMcpToolset

        assert not isinstance(milvus_scanner.milvus_agent.tools[0], CachedMcpToolset)
