import pathlib

ROOT_DIR = pathlib.Path(__file__).parent.parent

APP_NAME = "data_agent"
MODEL_NAME_OR_ID = "019f27d3-e606-7ed2-92e9-c49d5cfe1370"  # Gemma4

USER_AUTHOR = "user"
SYSTEM_AUTHOR = "system"

SESSION_TITLE_KEY = "session_title"

SYSTEM_APP_NAME = "system_agent"
SYSTEM_MODEL_NAME_OR_ID = "019f27d3-e606-7ed2-92e9-c49d5cfe1370"  # Gemma4

MILVUS_IMAGE_SEARCH_TOOL = "mcp_milvus_extract_embeddings_and_vector_search"
