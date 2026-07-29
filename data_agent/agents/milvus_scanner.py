from fabrix.adk.models import build_model
from google.adk.agents.llm_agent import Agent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

from common.config import SETTINGS
from common.constants import MODEL_NAME_OR_ID
from data_agent.agents.callbacks import inject_pending_image
from data_agent.agents.prompts.milvus_scanner import MILVUS_AGENT_NAME, MILVUS_AGENT_INSTRUCTION

milvus_model = build_model(MODEL_NAME_OR_ID)

milvus_agent = Agent(
    model=milvus_model,
    name=MILVUS_AGENT_NAME,
    instruction=MILVUS_AGENT_INSTRUCTION,
    before_tool_callback=inject_pending_image,
    tools=[
        McpToolset(connection_params=StreamableHTTPConnectionParams(
            url=f"http://{SETTINGS.milvus_mcp.host}:{SETTINGS.milvus_mcp.port}/mcp")
        )
    ]
)
