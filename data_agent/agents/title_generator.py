from fabrix.adk.factory import create_fabrix_app
from fabrix.adk.models import build_model
from google.adk.agents.llm_agent import Agent

from common.constants import SYSTEM_MODEL_NAME_OR_ID, SYSTEM_APP_NAME
from data_agent.agents.prompts.title_generator import SYSTEM_AGENT_NAME, SYSTEM_AGENT_INSTRUCTION

system_model = build_model(SYSTEM_MODEL_NAME_OR_ID)

system_agent = Agent(
    model=system_model,
    name=SYSTEM_AGENT_NAME,
    instruction=SYSTEM_AGENT_INSTRUCTION
)

system_app = create_fabrix_app(system_agent, app_name=SYSTEM_APP_NAME)
