import logging
from typing import Annotated
from fastapi import APIRouter, status, HTTPException, Path, Depends

from data_agent.dependencies import get_db_session_service, require_path_user
from data_agent.schemas import (
    SessionInfo, ListSessionsResponse, CreateSessionResponse, RenameSessionRequest, CreateSessionTitleResponse
)
from data_agent.services import DBSessionService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/apps", tags=["sessions"], dependencies=[Depends(require_path_user)])


@router.get(
    "/users/{user_id}/sessions",
    response_model=ListSessionsResponse,
    status_code=status.HTTP_200_OK
)
async def list_sessions(
        user_id: Annotated[str, Path()],
        db_session_service: Annotated[DBSessionService, Depends(get_db_session_service)]
):
    try:
        return await db_session_service.list_sessions(user_id=user_id)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/users/{user_id}/sessions",
    response_model=CreateSessionResponse,
    status_code=status.HTTP_200_OK
)
async def create_session(
        user_id: Annotated[str, Path()],
        db_session_service: Annotated[DBSessionService, Depends(get_db_session_service)]
):
    try:
        return await db_session_service.create_session(user_id=user_id)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post(
    "/users/{user_id}/sessions/{session_id}/title",
    response_model=CreateSessionTitleResponse,
    status_code=status.HTTP_200_OK
)
async def create_session_title(
        user_id: Annotated[str, Path()],
        session_id: Annotated[str, Path()],
        db_session_service: Annotated[DBSessionService, Depends(get_db_session_service)]
):
    try:
        return await db_session_service.create_session_title(user_id, session_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.patch(
    "/users/{user_id}/sessions/{session_id}/title",
    status_code=status.HTTP_200_OK
)
async def rename_session_title(
        user_id: Annotated[str, Path()],
        session_id: Annotated[str, Path()],
        request: Annotated[RenameSessionRequest, Depends()],
        db_session_service: Annotated[DBSessionService, Depends(get_db_session_service)]
):
    try:
        await db_session_service.rename_session_title(user_id, session_id, request)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/users/{user_id}/sessions/{session_id}",
    response_model=SessionInfo,
    status_code=status.HTTP_200_OK
)
async def get_session(
        user_id: Annotated[str, Path()],
        session_id: Annotated[str, Path()],
        db_session_service: Annotated[DBSessionService, Depends(get_db_session_service)]
):
    try:
        return await db_session_service.get_session(user_id=user_id, session_id=session_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete(
    "/users/{user_id}/sessions/{session_id}",
    status_code=status.HTTP_200_OK
)
async def delete_session(
        user_id: Annotated[str, Path()],
        session_id: Annotated[str, Path()],
        db_session_service: Annotated[DBSessionService, Depends(get_db_session_service)]
):
    try:
        await db_session_service.delete_session(user_id=user_id, session_id=session_id)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
