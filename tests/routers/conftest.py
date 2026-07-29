import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from data_agent.routers import router


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(router)
    return application


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client
