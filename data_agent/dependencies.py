from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Path, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.adk.sessions import BaseSessionService

from common.config import SETTINGS
from data_agent.schemas import CurrentUser
from data_agent.services import (
    AgentRunner, AuthError, AuthService, DBSessionService, OSArtifactService, SystemRunner,
    create_session_store, current_fabrix_token
)
from data_agent.storage import ObjectStorage

_bearer_scheme = HTTPBearer(auto_error=False)


@lru_cache
def get_object_storage() -> ObjectStorage:
    return ObjectStorage()


@lru_cache
def get_session_store() -> BaseSessionService:
    return create_session_store()


@lru_cache
def get_db_session_service() -> DBSessionService:
    return DBSessionService(session_service=get_session_store(), system_runner=SystemRunner())


@lru_cache
def get_agent_runner() -> AgentRunner:
    return AgentRunner(
        session_service=get_session_store(),
        artifact_service=OSArtifactService(storage=get_object_storage())
    )


@lru_cache
def get_auth_service() -> AuthService:
    return AuthService()


async def get_current_user(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
        auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> CurrentUser:
    if not SETTINGS.auth.enabled:
        return CurrentUser(id="local-dev", email="", name="Local Dev", token="", expires_at=0)

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Provide 'Authorization: Bearer <fabrix access token>'.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user = auth_service.user_from_token(credentials.credentials)
    except AuthError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
            headers={"WWW-Authenticate": "Bearer"},
        )

    current_fabrix_token.set(user.token)
    return user


async def require_path_user(
        user_id: Annotated[str, Path()],
        current_user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    """Guard for routes with a /users/{user_id}/ path: the caller may only act as themselves."""
    if SETTINGS.auth.enabled and current_user.id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own resources.",
        )
    return current_user
