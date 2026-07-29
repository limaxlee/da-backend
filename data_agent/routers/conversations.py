import time
import logging
from typing import Annotated
from fastapi import APIRouter, status, HTTPException, Path, Depends, UploadFile, File

from data_agent.dependencies import conversation_service
from data_agent.schemas import RunAgentRequest, RunAgentResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/apps", tags=["conversations"])


@router.post(
    "/users/{user_id}/sessions/{session_id}/run",
    response_model=RunAgentResponse,
    status_code=status.HTTP_200_OK
)
async def run(
        user_id: Annotated[str, Path()],
        session_id: Annotated[str, Path()],
        request: Annotated[RunAgentRequest, Depends()],
        image_file: UploadFile | None = File(None),
):
    t0 = time.monotonic()
    logger.info(f"[TIMING] /run START session={session_id} query={request.query!r}")
    try:
        result = await conversation_service.run(
            user_id=user_id,
            session_id=session_id,
            request=request,
            image_file=image_file
        )
        logger.info(f"[TIMING] /run END session={session_id} elapsed={time.monotonic()-t0:.2f}s")
        return result
    except Exception as e:
        logger.info(f"[TIMING] /run FAILED session={session_id} elapsed={time.monotonic()-t0:.2f}s")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
