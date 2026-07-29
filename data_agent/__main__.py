from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from common.config import SETTINGS
from data_agent.dependencies import object_storage
from data_agent.routers import router
from data_agent.utils import initialize_logger

logger = initialize_logger("cosmo_data_agent.log")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting COSMO Data Agent Backend")
    await object_storage.connect()
    try:
        yield
    finally:
        await object_storage.disconnect()


app = FastAPI(title="COSMO Data Agent Backend", lifespan=lifespan)
app.include_router(router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=SETTINGS.server_port, log_config=None)
