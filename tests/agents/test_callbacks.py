from common.constants import MILVUS_IMAGE_SEARCH_TOOL
from data_agent.agents.callbacks import inject_pending_image


def test_inject_pending_image(mocker):
    image_tool = mocker.Mock()
    image_tool.name = MILVUS_IMAGE_SEARCH_TOOL
    other_tool = mocker.Mock()
    other_tool.name = "some_other_tool"
    pending_image = {"key": "app/u1/s1/img.png/0", "filename": "img.png", "content_type": "image/png"}

    args = {}
    tool_context = mocker.Mock(state={"pending_image": pending_image})
    assert inject_pending_image(other_tool, args, tool_context) is None
    assert args == {}

    args = {}
    tool_context = mocker.Mock(state={})
    assert inject_pending_image(image_tool, args, tool_context) is None
    assert args == {}

    args = {"query": "find similar"}
    tool_context = mocker.Mock(state={"pending_image": pending_image})
    assert inject_pending_image(image_tool, args, tool_context) is None
    assert args == {
        "query": "find similar",
        "data_uri": "app/u1/s1/img.png/0",
        "filename": "img.png",
        "content_type": "image/png",
    }
