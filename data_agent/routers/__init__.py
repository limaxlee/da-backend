from fastapi import APIRouter

from .auth import alias_router as auth_alias_router
from .auth import router as auth_router
from .health import router as health_router
from .runner import router as runner_router
from .session import router as session_router

router = APIRouter()
router.include_router(health_router)
router.include_router(auth_router)
router.include_router(auth_alias_router)
router.include_router(session_router)
router.include_router(runner_router)
