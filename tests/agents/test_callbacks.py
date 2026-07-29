import pytest

from data_agent.agents.callbacks import MILVUS_IMAGE_SEARCH_TOOL, inject_pending_image

OBJECT_KEY = "data_agent/user-1/session-1/photo.png/0"
FILENAME = "photo.png"
CONTENT_TYPE = "image/png"
PENDING_IMAGE = {"key": OBJECT_KEY, "filename": FILENAME, "content_type": CONTENT_TYPE}


@pytest.fixture
def image_search_tool(mocker):
    tool = mocker.MagicMock()
    tool.name = MILVUS_IMAGE_SEARCH_TOOL
    return tool


@pytest.fixture
def tool_context(mocker):
    context = mocker.MagicMock()
    context.state = {"pending_image": PENDING_IMAGE}
    return context


class TestInjectPendingImage:

    def test_injects_the_pending_image_into_the_tool_arguments(
        self, image_search_tool, tool_context
    ):
        args = {"top_k": 5}

        result = inject_pending_image(image_search_tool, args, tool_context)

        assert result is None
        assert args == {
            "top_k": 5,
            "data_uri": OBJECT_KEY,
            "filename": FILENAME,
            "content_type": CONTENT_TYPE,
        }

    def test_overwrites_existing_image_arguments(
        self, image_search_tool, tool_context
    ):
        args = {"data_uri": "stale", "filename": "old.png", "content_type": "image/gif"}

        inject_pending_image(image_search_tool, args, tool_context)

        assert args["data_uri"] == OBJECT_KEY
        assert args["filename"] == FILENAME
        assert args["content_type"] == CONTENT_TYPE

    def test_ignores_other_tools(self, mocker, tool_context):
        other_tool = mocker.MagicMock()
        other_tool.name = "mcp_mongodb_find"
        args = {"query": {}}

        result = inject_pending_image(other_tool, args, tool_context)

        assert result is None
        assert args == {"query": {}}

    def test_does_not_read_state_for_other_tools(self, mocker):
        other_tool = mocker.MagicMock()
        other_tool.name = "mcp_mongodb_find"
        context = mocker.MagicMock()

        inject_pending_image(other_tool, {}, context)

        context.state.get.assert_not_called()

    def test_reads_the_pending_image_from_session_state(
        self, mocker, image_search_tool
    ):
        context = mocker.MagicMock()
        context.state.get.return_value = PENDING_IMAGE

        inject_pending_image(image_search_tool, {}, context)

        context.state.get.assert_called_once_with("pending_image")

    def test_leaves_arguments_untouched_when_no_image_is_pending(
        self, mocker, image_search_tool
    ):
        context = mocker.MagicMock()
        context.state = {}
        args = {"top_k": 5}

        result = inject_pending_image(image_search_tool, args, context)

        assert result is None
        assert args == {"top_k": 5}

    @pytest.mark.parametrize("pending", [None, {}, ""])
    def test_treats_falsy_state_as_no_pending_image(
        self, mocker, image_search_tool, pending
    ):
        context = mocker.MagicMock()
        context.state = {"pending_image": pending}
        args = {}

        inject_pending_image(image_search_tool, args, context)

        assert args == {}

    def test_warns_when_no_image_is_pending(self, mocker, image_search_tool):
        mock_logger = mocker.patch("data_agent.agents.callbacks.logger")
        context = mocker.MagicMock()
        context.state = {}

        inject_pending_image(image_search_tool, {}, context)

        mock_logger.warning.assert_called_once()

    def test_does_not_warn_for_other_tools(self, mocker):
        mock_logger = mocker.patch("data_agent.agents.callbacks.logger")
        other_tool = mocker.MagicMock()
        other_tool.name = "mcp_mongodb_find"

        inject_pending_image(other_tool, {}, mocker.MagicMock())

        mock_logger.warning.assert_not_called()

    def test_raises_when_the_pending_image_is_incomplete(
        self, mocker, image_search_tool
    ):
        context = mocker.MagicMock()
        context.state = {"pending_image": {"key": OBJECT_KEY}}

        with pytest.raises(KeyError):
            inject_pending_image(image_search_tool, {}, context)

    def test_tool_name_constant(self):
        assert MILVUS_IMAGE_SEARCH_TOOL == (
            "mcp_milvus_extract_embeddings_and_vector_search"
        )
