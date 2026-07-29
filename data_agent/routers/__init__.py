from fastapi import APIRouter

from .conversations import router as conversations_router
from .health import router as health_router
from .sessions import router as sessions_router

router = APIRouter()
router.include_router(health_router)
router.include_router(sessions_router)
router.include_router(conversations_router)
