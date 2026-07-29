import logging

logger = logging.getLogger(__name__)

MILVUS_IMAGE_SEARCH_TOOL = "mcp_milvus_extract_embeddings_and_vector_search"


def inject_pending_image(tool, args, tool_context):
    if tool.name != MILVUS_IMAGE_SEARCH_TOOL:
        return None

    info = tool_context.state.get("pending_image")

    # --- ALTERNATIVE (turn-scoped pending image) ----------------------------------------------
    # Pairs with the state_delta version in ConversationService.run. With the "temp:" prefix the
    # key is absent on turns without an upload, so the guard below becomes a live check instead of
    # dead code (today it can only fire before the first upload of a session).
    #
    # info = tool_context.state.get(PENDING_IMAGE_KEY)
    # ------------------------------------------------------------------------------------------

    if not info:
        logger.warning("Image search tool called but no pending image")
        return None

    args["data_uri"] = info["key"]
    args["filename"] = info["filename"]
    args["content_type"] = info["content_type"]

    return None
