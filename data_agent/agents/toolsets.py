import logging
from typing import List, Optional

from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools import BaseTool
from google.adk.tools.mcp_tool import McpToolset

logger = logging.getLogger(__name__)


class CachedMcpToolset(McpToolset):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cached_tools = None
        logger.debug(f"CachedMcpToolset instance created: {id(self)}")

    async def get_tools(self, readonly_context: Optional[ReadonlyContext] = None) -> List[BaseTool]:
        if self._cached_tools is None:
            self._cached_tools = await super().get_tools(readonly_context)
        return self._cached_tools
