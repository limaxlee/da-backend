import pytest

from common.config import SETTINGS
from data_agent.storage.object_storage import ObjectStorage


async def _pages(items):
    for item in items:
        yield item


class _AsyncContext:
    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *args):
        return False


@pytest.fixture
def storage():
    return ObjectStorage()


@pytest.fixture
def client(mocker, storage):
    s3_client = mocker.Mock(
        put_object=mocker.AsyncMock(),
        get_object=mocker.AsyncMock(),
        head_object=mocker.AsyncMock(),
        delete_objects=mocker.AsyncMock(),
    )
    storage._client = s3_client
    return s3_client


class TestObjectStorage:
    def test_client(self, storage, mocker):
        with pytest.raises(RuntimeError):
            _ = storage.client

        s3_client = mocker.Mock()
        storage._client = s3_client
        assert storage.client is s3_client

    @pytest.mark.asyncio
    async def test_connect(self, mocker, storage):
        s3_client = mocker.Mock()
        create_client = mocker.patch.object(
            storage._session, "create_client", return_value=_AsyncContext(s3_client)
        )

        result = await storage.connect()

        assert result is storage
        assert storage._client is s3_client
        create_client.assert_called_once()
        kwargs = create_client.call_args.kwargs
        assert kwargs["endpoint_url"] == SETTINGS.object_storage.endpoint
        assert kwargs["aws_access_key_id"] == SETTINGS.object_storage.access_key
        assert kwargs["aws_secret_access_key"] == SETTINGS.object_storage.secret_key

        await storage.connect()
        create_client.assert_called_once()

    @pytest.mark.asyncio
    async def test_close(self, mocker, storage):
        aclose = mocker.patch.object(storage._exit_stack, "aclose", mocker.AsyncMock())

        await storage.close()
        aclose.assert_not_awaited()

        storage._client = mocker.Mock()
        await storage.close()
        aclose.assert_awaited_once()
        assert storage._client is None

    @pytest.mark.asyncio
    async def test_list_paginated_objects(self, mocker, storage, client):
        pages = [
            {"KeyCount": 2, "Contents": [{"Key": "prefix/a"}, {"Key": "prefix/b"}]},
            {"KeyCount": 0},
        ]
        paginator = mocker.Mock(paginate=mocker.Mock(return_value=_pages(pages)))
        client.get_paginator = mocker.Mock(return_value=paginator)

        result = await storage.list_paginated_objects(prefix="prefix/", max_items=5)

        assert result == ["prefix/a", "prefix/b"]
        paginator.paginate.assert_called_once_with(
            Bucket=SETTINGS.object_storage.bucket,
            Prefix="prefix/",
            PaginationConfig={"MaxItems": 5},
        )

        client.get_paginator = mocker.Mock(side_effect=RuntimeError("boom"))
        assert await storage.list_paginated_objects(prefix="prefix/") is None

    @pytest.mark.asyncio
    async def test_upload_object(self, mocker, storage, client):
        client.put_object.return_value = {"ResponseMetadata": {"RequestId": "req-1"}}

        assert await storage.upload_object(b"payload", key="k", content_type="image/png") is True
        client.put_object.assert_awaited_once_with(
            Bucket=SETTINGS.object_storage.bucket, Body=b"payload", Key="k", ContentType="image/png"
        )

        opened = mocker.MagicMock()
        opened.__aenter__.return_value = mocker.Mock(read=mocker.AsyncMock(return_value=b"from-file"))
        mocker.patch("data_agent.storage.object_storage.aiofiles.open", return_value=opened)
        assert await storage.upload_object("some/path.bin", key="k2") is True
        assert client.put_object.call_args.kwargs["Body"] == b"from-file"
        assert "ContentType" not in client.put_object.call_args.kwargs

        assert await storage.upload_object(123, key="k3") is False

        client.put_object.side_effect = RuntimeError("boom")
        assert await storage.upload_object(b"payload", key="k4") is False

    @pytest.mark.asyncio
    async def test_retrieve_object(self, mocker, storage, client):
        stream = mocker.Mock(read=mocker.AsyncMock(return_value=b"content"))
        client.get_object.return_value = {
            "Body": _AsyncContext(stream),
            "ResponseMetadata": {"RequestId": "req-1"},
        }

        assert await storage.retrieve_object(key="k") == b"content"
        client.get_object.assert_awaited_once_with(Bucket=SETTINGS.object_storage.bucket, Key="k")

        client.get_object.side_effect = RuntimeError("boom")
        assert await storage.retrieve_object(key="k") is None

    @pytest.mark.asyncio
    async def test_retrieve_object_info(self, storage, client):
        info = {"ContentType": "image/png", "ContentLength": 3}
        client.head_object.return_value = info

        assert await storage.retrieve_object_info(key="k") == info
        client.head_object.assert_awaited_once_with(Bucket=SETTINGS.object_storage.bucket, Key="k")

        client.head_object.side_effect = RuntimeError("boom")
        assert await storage.retrieve_object_info(key="k") is None

    @pytest.mark.asyncio
    async def test_delete_objects(self, storage, client):
        client.delete_objects.return_value = {
            "Deleted": [{"Key": "k"}],
            "ResponseMetadata": {"RequestId": "req-1"},
        }
        keys = [f"key-{i}" for i in range(1500)]

        assert await storage.delete_objects(keys) is True
        assert client.delete_objects.await_count == 2
        first_batch = client.delete_objects.await_args_list[0].kwargs["Delete"]["Objects"]
        second_batch = client.delete_objects.await_args_list[1].kwargs["Delete"]["Objects"]
        assert len(first_batch) == 1000
        assert len(second_batch) == 500

        client.delete_objects.side_effect = RuntimeError("boom")
        assert await storage.delete_objects(["k"]) is False
