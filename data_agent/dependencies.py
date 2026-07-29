from data_agent.services import ConversationService, SessionService, TitleService, create_session_store
from data_agent.storage import ObjectStorageArtifactService, ObjectStorageClient

_session_store = create_session_store()

object_storage = ObjectStorageClient()
_artifact_service = ObjectStorageArtifactService(storage=object_storage)

session_service = SessionService(sessions=_session_store, titles=TitleService())
conversation_service = ConversationService(
    sessions=_session_store,
    artifacts=_artifact_service,
    storage=object_storage
)


def get_session_service() -> SessionService:
    return session_service


def get_conversation_service() -> ConversationService:
    return conversation_service
