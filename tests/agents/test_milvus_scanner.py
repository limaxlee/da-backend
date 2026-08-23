import data_agent.agents.milvus_scanner

from common.config import SETTINGS
from common.constants import MODEL_NAME_OR_ID
from data_agent.agents.callbacks import inject_pending_image
from data_agent.agents.prompts.milvus_scanner import MILVUS_AGENT_NAME, MILVUS_AGENT_INSTRUCTION


def test_milvus_agent(mocker, reload_module):
    build_model = mocker.patch("fabrix.adk.models.build_model")
    agent_cls = mocker.patch("google.adk.agents.llm_agent.Agent")
    toolset_cls = mocker.patch("google.adk.tools.mcp_tool.mcp_toolset.MCPToolset")
    params_cls = mocker.patch("google.adk.tools.mcp_tool.mcp_session_manager.StreamableHTTPConnectionParams")

    module = reload_module(data_agent.agents.milvus_scanner)

    build_model.assert_called_once_with(MODEL_NAME_OR_ID)
    params_cls.assert_called_once_with(
        url=f"http://{SETTINGS.milvus_mcp.host}:{SETTINGS.milvus_mcp.port}/mcp"
    )
    toolset_cls.assert_called_once_with(connection_params=params_cls.return_value)
    agent_cls.assert_called_once_with(
        model=build_model.return_value,
        name=MILVUS_AGENT_NAME,
        instruction=MILVUS_AGENT_INSTRUCTION,
        before_tool_callback=inject_pending_image,
        tools=[toolset_cls.return_value],
    )
    assert module.milvus_agent is agent_cls.return_value
