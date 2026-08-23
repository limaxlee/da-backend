import data_agent.agents.mongodb_scanner

from common.config import SETTINGS
from common.constants import MODEL_NAME_OR_ID
from data_agent.agents.prompts.mongodb_scanner import MONGODB_AGENT_NAME, MONGODB_AGENT_INSTRUCTION


def test_mongodb_agent(mocker, reload_module):
    build_model = mocker.patch("fabrix.adk.models.build_model")
    agent_cls = mocker.patch("google.adk.agents.llm_agent.Agent")
    toolset_cls = mocker.patch("google.adk.tools.mcp_tool.mcp_toolset.MCPToolset")
    params_cls = mocker.patch("google.adk.tools.mcp_tool.mcp_session_manager.StreamableHTTPConnectionParams")

    module = reload_module(data_agent.agents.mongodb_scanner)

    build_model.assert_called_once_with(MODEL_NAME_OR_ID)
    params_cls.assert_called_once_with(
        url=f"http://{SETTINGS.mongodb_mcp.host}:{SETTINGS.mongodb_mcp.port}/mcp"
    )
    toolset_cls.assert_called_once_with(connection_params=params_cls.return_value)
    agent_cls.assert_called_once_with(
        model=build_model.return_value,
        name=MONGODB_AGENT_NAME,
        instruction=MONGODB_AGENT_INSTRUCTION,
        tools=[toolset_cls.return_value],
    )
    assert module.mongodb_agent is agent_cls.return_value
