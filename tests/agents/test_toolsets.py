import pytest
from google.adk.tools.mcp_tool import McpToolset

from data_agent.agents.toolsets import CachedMcpToolset

pytestmark = pytest.mark.asyncio


@pytest.fixture
def tools(mocker):
    return [mocker.MagicMock(name="tool-a"), mocker.MagicMock(name="tool-b")]


@pytest.fixture
def mock_get_tools(mocker, tools):
    return mocker.patch.object(
        McpToolset, "get_tools", new=mocker.AsyncMock(return_value=tools)
    )


@pytest.fixture
def toolset():
    return CachedMcpToolset()


class TestInit:

    async def test_starts_with_an_empty_cache(self, toolset):
        assert toolset._cached_tools is None

    async def test_forwards_arguments_to_the_base_toolset(self, mocker):
        mock_init = mocker.patch.object(McpToolset, "__init__", return_value=None)
        connection_params = mocker.MagicMock()

        CachedMcpToolset(connection_params=connection_params)

        mock_init.assert_called_once_with(connection_params=connection_params)

    async def test_is_an_mcp_toolset(self, toolset):
        assert isinstance(toolset, McpToolset)


class TestGetTools:

    async def test_returns_the_tools_from_the_base_toolset(
        self, toolset, mock_get_tools, tools
    ):
        assert await toolset.get_tools() == tools

    async def test_caches_the_first_result(self, toolset, mock_get_tools, tools):
        first = await toolset.get_tools()
        second = await toolset.get_tools()

        assert first is second
        mock_get_tools.assert_awaited_once()

    async def test_stores_the_result_on_the_instance(
        self, toolset, mock_get_tools, tools
    ):
        await toolset.get_tools()

        assert toolset._cached_tools == tools

    async def test_passes_the_readonly_context_through(
        self, mocker, toolset, mock_get_tools
    ):
        context = mocker.MagicMock()

        await toolset.get_tools(context)

        mock_get_tools.assert_awaited_once_with(context)

    async def test_defaults_the_readonly_context_to_none(
        self, toolset, mock_get_tools
    ):
        await toolset.get_tools()

        mock_get_tools.assert_awaited_once_with(None)

    async def test_ignores_the_context_of_later_calls(
        self, mocker, toolset, mock_get_tools
    ):
        await toolset.get_tools(None)
        await toolset.get_tools(mocker.MagicMock())

        mock_get_tools.assert_awaited_once_with(None)

    async def test_caches_an_empty_result(self, mocker, toolset, tools):
        mock_get_tools = mocker.patch.object(
            McpToolset, "get_tools", new=mocker.AsyncMock(side_effect=[[], tools])
        )

        assert await toolset.get_tools() == []
        assert await toolset.get_tools() == []
        mock_get_tools.assert_awaited_once()

    async def test_each_instance_caches_separately(self, mocker, tools):
        other_tools = [mocker.MagicMock(name="tool-c")]
        mocker.patch.object(
            McpToolset, "get_tools", new=mocker.AsyncMock(side_effect=[tools, other_tools])
        )
        first = CachedMcpToolset()
        second = CachedMcpToolset()

        assert await first.get_tools() == tools
        assert await second.get_tools() == other_tools

    async def test_does_not_cache_a_failure(self, mocker, toolset, tools):
        mock_get_tools = mocker.patch.object(
            McpToolset,
            "get_tools",
            new=mocker.AsyncMock(side_effect=[RuntimeError("mcp down"), tools]),
        )

        with pytest.raises(RuntimeError, match="mcp down"):
            await toolset.get_tools()

        assert await toolset.get_tools() == tools
        assert mock_get_tools.await_count == 2
