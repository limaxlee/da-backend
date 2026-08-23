import pytest

import data_agent.__main__ as main


@pytest.mark.asyncio
async def test_lifespan(mocker):
    object_storage = mocker.Mock(connect=mocker.AsyncMock(), close=mocker.AsyncMock())
    mocker.patch.object(main, "get_object_storage", return_value=object_storage)
    get_db_session_service = mocker.patch.object(main, "get_db_session_service")
    get_agent_runner = mocker.patch.object(main, "get_agent_runner")

    async with main.lifespan(main.app):
        object_storage.connect.assert_awaited_once()
        get_db_session_service.assert_called_once_with()
        get_agent_runner.assert_called_once_with()
        object_storage.close.assert_not_awaited()

    object_storage.close.assert_awaited_once()
