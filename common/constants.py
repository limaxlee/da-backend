import pathlib

ROOT_DIR = pathlib.Path(__file__).parent.parent

APP_NAME = "data_agent"
MODEL_NAME_OR_ID = "Gemma4"

USER_AUTHOR = "user"

# --- ALTERNATIVE (turn-scoped pending image) ---------------------------------------------------
# Used by the commented state_delta version in ConversationService.run and inject_pending_image.
# The "temp:" prefix is an ADK state scope: the key is applied to the live session state for the
# current invocation but skipped when the session service persists the event.
#
# PENDING_IMAGE_KEY = "temp:pending_image"
# -----------------------------------------------------------------------------------------------

SYSTEM_APP_NAME = "system_agent"
SYSTEM_MODEL_NAME_OR_ID = "Gauss"
