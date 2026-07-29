from fabrix.adk.factory import create_fabrix_app
from fabrix.adk.models import build_model
from google.adk.agents.llm_agent import Agent
from google.adk.tools import AgentTool

from common.constants import MODEL_NAME_OR_ID, APP_NAME
from data_agent.agents.milvus_scanner import milvus_agent
from data_agent.agents.mongodb_scanner import mongodb_agent
from data_agent.agents.prompts.root_orchestrator import (
    ROOT_AGENT_NAME, ROOT_AGENT_DESCRIPTION, ROOT_AGENT_INSTRUCTION
)

root_model = build_model(MODEL_NAME_OR_ID)

root_agent = Agent(
    model=root_model,
    name=ROOT_AGENT_NAME,
    description=ROOT_AGENT_DESCRIPTION,
    instruction=ROOT_AGENT_INSTRUCTION,
    tools=[AgentTool(agent=milvus_agent), AgentTool(agent=mongodb_agent)]
)

agent_app = create_fabrix_app(root_agent, app_name=APP_NAME)
