from fabrix.adk.models import build_model
from google.adk.agents.llm_agent import Agent
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams

from common.config import SETTINGS
from common.constants import MODEL_NAME_OR_ID
from data_agent.agents.prompts.mongodb_scanner import MONGODB_AGENT_NAME, MONGODB_AGENT_INSTRUCTION
from data_agent.agents.toolsets import CachedMcpToolset

mongodb_model = build_model(MODEL_NAME_OR_ID)

mongodb_agent = Agent(
    model=mongodb_model,
    name=MONGODB_AGENT_NAME,
    instruction=MONGODB_AGENT_INSTRUCTION,
    tools=[
        CachedMcpToolset(connection_params=StreamableHTTPConnectionParams(
            url=f"http://{SETTINGS.mongodb_mcp.host}:{SETTINGS.mongodb_mcp.port}/mcp")
        )
    ]
)
