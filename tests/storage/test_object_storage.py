import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from data_agent.storage.object_storage import ObjectStorageClient

pytestmark = pytest.mark.asyncio

BUCKET = "test-bucket"
ENDPOINT = "https://storage.test"
ACCESS_KEY = "test-access-key"
SECRET_KEY = "test-secret-key"
REQUEST_ID = "req-1"

METADATA = {"ResponseMetadata": {"RequestId": REQUEST_ID}}


async def _async_iter(items):
    for item in items:
        yield item


def _client_error(operation="GetObject"):
    return ClientError({"Error": {"Code": "NoSuchKey", "Message": "missing"}}, operation)


@pytest.fixture
def mock_settings(mocker):
    settings = mocker.patch("data_agent.storage.object_storage.SETTINGS")
    settings.object_storage.bucket = BUCKET
    settings.object_storage.endpoint = ENDPOINT
    settings.object_storage.access_key = ACCESS_KEY
    settings.object_storage.secret_key = SECRET_KEY
    return settings


@pytest.fixture
def mock_session(mocker, mock_settings):
    session = mocker.MagicMock()
    mocker.patch(
        "data_agent.storage.object_storage.get_session", return_value=session
    )
    return session


@pytest.fixture
def storage(mock_session):
    return ObjectStorageClient()


@pytest.fixture
def s3_client(mocker):
    client = mocker.AsyncMock()
    client.get_paginator = mocker.MagicMock()
    return client


@pytest.fixture
def connected_storage(storage, s3_client):
    storage._client = s3_client
    return storage


def _paginator(mocker, s3_client, pages):
    paginator = mocker.MagicMock()
    paginator.paginate = mocker.MagicMock(return_value=_async_iter(pages))
    s3_client.get_paginator.return_value = paginator
    return paginator


class TestInit:

    async def test_reads_configuration_from_settings(self, storage):
        assert storage._config == {
            "bucket": BUCKET,
            "endpoint": ENDPOINT,
            "access_key": ACCESS_KEY,
            "secret_key": SECRET_KEY,
        }
        assert storage._bucket == BUCKET

    async def test_starts_disconnected(self, storage):
        assert storage._client is None

    async def test_client_property_raises_when_not_connected(self, storage):
        with pytest.raises(RuntimeError, match="not connected"):
            _ = storage.client

    async def test_client_property_returns_underlying_client(
        self, connected_storage, s3_client
    ):
        assert connected_storage.client is s3_client


class TestConnect:

    @pytest.fixture
    def client_context(self, mocker, mock_session, s3_client):
        context = mocker.MagicMock()
        context.__aenter__.return_value = s3_client
        mock_session.create_client.return_value = context
        return context

    async def test_creates_s3_client_with_configured_credentials(
        self, storage, mock_session, client_context, s3_client
    ):
        result = await storage.connect()

        mock_session.create_client.assert_called_once_with(
            "s3",
            endpoint_url=ENDPOINT,
            aws_access_key_id=ACCESS_KEY,
            aws_secret_access_key=SECRET_KEY,
        )
        assert result is storage
        assert storage.client is s3_client

    async def test_is_idempotent(self, storage, mock_session, client_context):
        await storage.connect()
        result = await storage.connect()

        mock_session.create_client.assert_called_once()
        assert result is storage

    async def test_reraises_client_error_and_stays_disconnected(
        self, mocker, storage, mock_session
    ):
        mock_session.create_client.side_effect = _client_error("CreateClient")
        mock_aclose = mocker.patch.object(
            storage._exit_stack, "aclose", new=mocker.AsyncMock()
        )

        with pytest.raises(ClientError):
            await storage.connect()

        mock_aclose.assert_awaited_once()
        assert storage._client is None

    async def test_reraises_botocore_error_and_stays_disconnected(
        self, mocker, storage, mock_session
    ):
        mock_session.create_client.side_effect = EndpointConnectionError(
            endpoint_url=ENDPOINT
        )
        mock_aclose = mocker.patch.object(
            storage._exit_stack, "aclose", new=mocker.AsyncMock()
        )

        with pytest.raises(EndpointConnectionError):
            await storage.connect()

        mock_aclose.assert_awaited_once()
        assert storage._client is None

    async def test_reraises_unexpected_error_and_stays_disconnected(
        self, mocker, storage, mock_session
    ):
        mock_session.create_client.side_effect = RuntimeError("boom")
        mock_aclose = mocker.patch.object(
            storage._exit_stack, "aclose", new=mocker.AsyncMock()
        )

        with pytest.raises(RuntimeError, match="boom"):
            await storage.connect()

        mock_aclose.assert_awaited_once()
        assert storage._client is None


class TestDisconnect:

    async def test_closes_exit_stack_and_clears_client(
        self, mocker, connected_storage
    ):
        mock_aclose = mocker.patch.object(
            connected_storage._exit_stack, "aclose", new=mocker.AsyncMock()
        )

        await connected_storage.disconnect()

        mock_aclose.assert_awaited_once()
        assert connected_storage._client is None

    async def test_is_a_noop_when_not_connected(self, mocker, storage):
        mock_aclose = mocker.patch.object(
            storage._exit_stack, "aclose", new=mocker.AsyncMock()
        )

        await storage.disconnect()

        mock_aclose.assert_not_awaited()


class TestAsyncContextManager:

    async def test_connects_on_enter_and_disconnects_on_exit(self, mocker, storage):
        mock_connect = mocker.patch.object(
            storage, "connect", new=mocker.AsyncMock(return_value=storage)
        )
        mock_disconnect = mocker.patch.object(
            storage, "disconnect", new=mocker.AsyncMock()
        )

        async with storage as entered:
            assert entered is storage
            mock_connect.assert_awaited_once()
            mock_disconnect.assert_not_awaited()

        mock_disconnect.assert_awaited_once()

    async def test_disconnects_when_body_raises(self, mocker, storage):
        mocker.patch.object(
            storage, "connect", new=mocker.AsyncMock(return_value=storage)
        )
        mock_disconnect = mocker.patch.object(
            storage, "disconnect", new=mocker.AsyncMock()
        )

        with pytest.raises(ValueError):
            async with storage:
                raise ValueError("inside")

        mock_disconnect.assert_awaited_once()


class TestCreateBucket:

    async def test_uses_default_bucket(self, connected_storage, s3_client):
        s3_client.create_bucket.return_value = METADATA

        assert await connected_storage.create_bucket() is True
        s3_client.create_bucket.assert_awaited_once_with(Bucket=BUCKET)

    async def test_uses_explicit_bucket(self, connected_storage, s3_client):
        s3_client.create_bucket.return_value = METADATA

        assert await connected_storage.create_bucket("other") is True
        s3_client.create_bucket.assert_awaited_once_with(Bucket="other")

    async def test_returns_false_on_error(self, connected_storage, s3_client):
        s3_client.create_bucket.side_effect = _client_error("CreateBucket")

        assert await connected_storage.create_bucket() is False

    async def test_returns_false_when_not_connected(self, storage):
        assert await storage.create_bucket() is False


class TestListBuckets:

    async def test_returns_bucket_names(self, connected_storage, s3_client):
        s3_client.list_buckets.return_value = {
            **METADATA,
            "Buckets": [{"Name": "first"}, {"Name": "second"}],
        }

        assert await connected_storage.list_buckets() == ["first", "second"]

    async def test_returns_empty_list_when_no_buckets(
        self, connected_storage, s3_client
    ):
        s3_client.list_buckets.return_value = METADATA

        assert await connected_storage.list_buckets() == []

    async def test_returns_none_on_error(self, connected_storage, s3_client):
        s3_client.list_buckets.side_effect = _client_error("ListBuckets")

        assert await connected_storage.list_buckets() is None


class TestListPaginatedObjects:

    async def test_collects_keys_across_pages(
        self, mocker, connected_storage, s3_client
    ):
        _paginator(mocker, s3_client, [
            {"KeyCount": 2, "Contents": [{"Key": "a"}, {"Key": "b"}]},
            {"KeyCount": 1, "Contents": [{"Key": "c"}]},
        ])

        assert await connected_storage.list_paginated_objects() == ["a", "b", "c"]

    async def test_skips_empty_pages(self, mocker, connected_storage, s3_client):
        _paginator(mocker, s3_client, [
            {"KeyCount": 0},
            {"KeyCount": 1, "Contents": [{"Key": "a"}]},
        ])

        assert await connected_storage.list_paginated_objects() == ["a"]

    async def test_passes_prefix_and_pagination_config(
        self, mocker, connected_storage, s3_client
    ):
        paginator = _paginator(mocker, s3_client, [])

        await connected_storage.list_paginated_objects(
            prefix="images/", max_items=25, bucket="other"
        )

        s3_client.get_paginator.assert_called_once_with("list_objects_v2")
        paginator.paginate.assert_called_once_with(
            Bucket="other",
            Prefix="images/",
            PaginationConfig={"MaxItems": 25},
        )

    async def test_defaults_to_configured_bucket_and_empty_prefix(
        self, mocker, connected_storage, s3_client
    ):
        paginator = _paginator(mocker, s3_client, [])

        await connected_storage.list_paginated_objects()

        paginator.paginate.assert_called_once_with(
            Bucket=BUCKET,
            Prefix="",
            PaginationConfig={"MaxItems": 100},
        )

    async def test_returns_none_on_error(self, mocker, connected_storage, s3_client):
        s3_client.get_paginator.side_effect = _client_error("ListObjectsV2")

        assert await connected_storage.list_paginated_objects() is None

    async def test_returns_none_on_malformed_page(
        self, mocker, connected_storage, s3_client
    ):
        _paginator(mocker, s3_client, [{"Contents": [{"Key": "a"}]}])

        assert await connected_storage.list_paginated_objects() is None


class TestDeleteBucket:

    async def test_deletes_default_bucket(self, connected_storage, s3_client):
        s3_client.delete_bucket.return_value = METADATA

        assert await connected_storage.delete_bucket() is True
        s3_client.delete_bucket.assert_awaited_once_with(Bucket=BUCKET)

    async def test_deletes_explicit_bucket(self, connected_storage, s3_client):
        s3_client.delete_bucket.return_value = METADATA

        assert await connected_storage.delete_bucket("other") is True
        s3_client.delete_bucket.assert_awaited_once_with(Bucket="other")

    async def test_returns_false_on_error(self, connected_storage, s3_client):
        s3_client.delete_bucket.side_effect = _client_error("DeleteBucket")

        assert await connected_storage.delete_bucket() is False


class TestUploadObject:

    async def test_uploads_bytes(self, connected_storage, s3_client):
        s3_client.put_object.return_value = METADATA

        result = await connected_storage.upload_object(b"payload", key="dir/file")

        assert result is True
        s3_client.put_object.assert_awaited_once_with(
            Bucket=BUCKET, Body=b"payload", Key="dir/file"
        )

    async def test_includes_content_type_when_provided(
        self, connected_storage, s3_client
    ):
        s3_client.put_object.return_value = METADATA

        await connected_storage.upload_object(
            b"payload", key="dir/file", content_type="image/png"
        )

        s3_client.put_object.assert_awaited_once_with(
            Bucket=BUCKET, Body=b"payload", Key="dir/file", ContentType="image/png"
        )

    async def test_reads_file_from_path(self, mocker, connected_storage, s3_client):
        s3_client.put_object.return_value = METADATA
        file_handle = mocker.AsyncMock()
        file_handle.read.return_value = b"file-content"
        file_context = mocker.MagicMock()
        file_context.__aenter__.return_value = file_handle
        mock_open = mocker.patch(
            "data_agent.storage.object_storage.aiofiles.open",
            return_value=file_context,
        )

        result = await connected_storage.upload_object("/tmp/photo.png", key="photo")

        assert result is True
        mock_open.assert_called_once_with("/tmp/photo.png", "rb")
        s3_client.put_object.assert_awaited_once_with(
            Bucket=BUCKET, Body=b"file-content", Key="photo"
        )

    async def test_uses_explicit_bucket(self, connected_storage, s3_client):
        s3_client.put_object.return_value = METADATA

        await connected_storage.upload_object(b"payload", key="k", bucket="other")

        assert s3_client.put_object.await_args.kwargs["Bucket"] == "other"

    async def test_returns_false_for_unsupported_type(
        self, connected_storage, s3_client
    ):
        assert await connected_storage.upload_object(123, key="k") is False
        s3_client.put_object.assert_not_awaited()

    async def test_returns_false_when_read_fails(
        self, mocker, connected_storage, s3_client
    ):
        mocker.patch(
            "data_agent.storage.object_storage.aiofiles.open",
            side_effect=FileNotFoundError("missing"),
        )

        assert await connected_storage.upload_object("/tmp/missing", key="k") is False
        s3_client.put_object.assert_not_awaited()

    async def test_returns_false_on_error(self, connected_storage, s3_client):
        s3_client.put_object.side_effect = _client_error("PutObject")

        assert await connected_storage.upload_object(b"payload", key="k") is False


class TestCopyObject:

    async def test_copies_within_bucket(self, connected_storage, s3_client):
        s3_client.copy_object.return_value = METADATA

        result = await connected_storage.copy_object("dest", "source")

        assert result is True
        s3_client.copy_object.assert_awaited_once_with(
            Bucket=BUCKET,
            Key="dest",
            CopySource={"Bucket": BUCKET, "Key": "source"},
        )

    async def test_uses_explicit_bucket_for_both_sides(
        self, connected_storage, s3_client
    ):
        s3_client.copy_object.return_value = METADATA

        await connected_storage.copy_object("dest", "source", bucket="other")

        s3_client.copy_object.assert_awaited_once_with(
            Bucket="other",
            Key="dest",
            CopySource={"Bucket": "other", "Key": "source"},
        )

    async def test_returns_false_on_error(self, connected_storage, s3_client):
        s3_client.copy_object.side_effect = _client_error("CopyObject")

        assert await connected_storage.copy_object("dest", "source") is False


class TestRetrieveObject:

    @pytest.fixture
    def body(self, mocker, s3_client):
        stream = mocker.AsyncMock()
        stream.read.return_value = b"payload"
        body = mocker.MagicMock()
        body.__aenter__.return_value = stream
        s3_client.get_object.return_value = {**METADATA, "Body": body}
        return body

    async def test_returns_object_data(self, connected_storage, s3_client, body):
        result = await connected_storage.retrieve_object("dir/file")

        assert result == b"payload"
        s3_client.get_object.assert_awaited_once_with(Bucket=BUCKET, Key="dir/file")

    async def test_uses_explicit_bucket(self, connected_storage, s3_client, body):
        await connected_storage.retrieve_object("dir/file", bucket="other")

        s3_client.get_object.assert_awaited_once_with(Bucket="other", Key="dir/file")

    async def test_closes_the_stream(self, connected_storage, body):
        await connected_storage.retrieve_object("dir/file")

        body.__aexit__.assert_awaited_once()

    async def test_returns_none_on_error(self, connected_storage, s3_client):
        s3_client.get_object.side_effect = _client_error()

        assert await connected_storage.retrieve_object("missing") is None


class TestRetrieveObjectInChunks:

    @pytest.fixture
    def body(self, mocker, s3_client):
        body = mocker.MagicMock()
        s3_client.get_object.return_value = {**METADATA, "Body": body}
        return body

    async def test_yields_every_chunk(self, mocker, connected_storage, body):
        body.iter_chunks = mocker.MagicMock(
            return_value=_async_iter([b"one", b"two", b"three"])
        )

        stream = await connected_storage.retrieve_object_in_chunks("dir/file")

        assert [chunk async for chunk in stream] == [b"one", b"two", b"three"]
        body.iter_chunks.assert_called_once_with(1024 * 1024)

    async def test_skips_empty_chunks(self, mocker, connected_storage, body):
        body.iter_chunks = mocker.MagicMock(
            return_value=_async_iter([b"one", b"", b"two"])
        )

        stream = await connected_storage.retrieve_object_in_chunks("dir/file")

        assert [chunk async for chunk in stream] == [b"one", b"two"]

    async def test_requests_the_configured_bucket(
        self, mocker, connected_storage, s3_client, body
    ):
        body.iter_chunks = mocker.MagicMock(return_value=_async_iter([]))

        await connected_storage.retrieve_object_in_chunks("dir/file")

        s3_client.get_object.assert_awaited_once_with(Bucket=BUCKET, Key="dir/file")

    async def test_returns_none_on_error(self, connected_storage, s3_client):
        s3_client.get_object.side_effect = _client_error()

        assert await connected_storage.retrieve_object_in_chunks("missing") is None


class TestRetrieveObjectInfo:

    async def test_returns_head_object_response(self, connected_storage, s3_client):
        s3_client.head_object.return_value = {**METADATA, "ContentType": "image/png"}

        result = await connected_storage.retrieve_object_info("dir/file")

        assert result["ContentType"] == "image/png"
        s3_client.head_object.assert_awaited_once_with(Bucket=BUCKET, Key="dir/file")

    async def test_uses_explicit_bucket(self, connected_storage, s3_client):
        s3_client.head_object.return_value = METADATA

        await connected_storage.retrieve_object_info("dir/file", bucket="other")

        s3_client.head_object.assert_awaited_once_with(Bucket="other", Key="dir/file")

    async def test_returns_none_on_error(self, connected_storage, s3_client):
        s3_client.head_object.side_effect = _client_error("HeadObject")

        assert await connected_storage.retrieve_object_info("missing") is None


class TestDeleteObject:

    async def test_deletes_from_default_bucket(self, connected_storage, s3_client):
        assert await connected_storage.delete_object("dir/file") is True
        s3_client.delete_object.assert_awaited_once_with(Bucket=BUCKET, Key="dir/file")

    async def test_deletes_from_explicit_bucket(self, connected_storage, s3_client):
        assert await connected_storage.delete_object("dir/file", "other") is True
        s3_client.delete_object.assert_awaited_once_with(
            Bucket="other", Key="dir/file"
        )

    async def test_returns_false_on_error(self, connected_storage, s3_client):
        s3_client.delete_object.side_effect = _client_error("DeleteObject")

        assert await connected_storage.delete_object("dir/file") is False


class TestDeleteObjects:

    async def test_deletes_all_keys_in_one_request(
        self, connected_storage, s3_client
    ):
        s3_client.delete_objects.return_value = {
            **METADATA,
            "Deleted": [{"Key": "a"}, {"Key": "b"}],
        }

        assert await connected_storage.delete_objects(["a", "b"]) is True
        s3_client.delete_objects.assert_awaited_once_with(
            Bucket=BUCKET, Delete={"Objects": [{"Key": "a"}, {"Key": "b"}]}
        )

    async def test_batches_keys_in_groups_of_1000(
        self, connected_storage, s3_client
    ):
        s3_client.delete_objects.return_value = METADATA
        keys = [f"key-{index}" for index in range(2500)]

        assert await connected_storage.delete_objects(keys) is True
        assert s3_client.delete_objects.await_count == 3

        batch_sizes = [
            len(call.kwargs["Delete"]["Objects"])
            for call in s3_client.delete_objects.await_args_list
        ]
        assert batch_sizes == [1000, 1000, 500]

    async def test_empty_key_list_makes_no_request(
        self, connected_storage, s3_client
    ):
        assert await connected_storage.delete_objects([]) is True
        s3_client.delete_objects.assert_not_awaited()

    async def test_uses_explicit_bucket(self, connected_storage, s3_client):
        s3_client.delete_objects.return_value = METADATA

        await connected_storage.delete_objects(["a"], bucket="other")

        assert s3_client.delete_objects.await_args.kwargs["Bucket"] == "other"

    async def test_returns_false_on_error(self, connected_storage, s3_client):
        s3_client.delete_objects.side_effect = _client_error("DeleteObjects")

        assert await connected_storage.delete_objects(["a"]) is False


class TestGetBucketSize:

    async def test_sums_object_sizes_across_pages(
        self, mocker, connected_storage, s3_client
    ):
        _paginator(mocker, s3_client, [
            {"Contents": [{"Size": 100}, {"Size": 50}]},
            {"Contents": [{"Size": 25}]},
        ])

        assert await connected_storage.get_bucket_size() == 175

    async def test_skips_pages_without_contents(
        self, mocker, connected_storage, s3_client
    ):
        _paginator(mocker, s3_client, [{}, {"Contents": [{"Size": 10}]}])

        assert await connected_storage.get_bucket_size() == 10

    async def test_returns_zero_for_empty_bucket(
        self, mocker, connected_storage, s3_client
    ):
        _paginator(mocker, s3_client, [])

        assert await connected_storage.get_bucket_size() == 0

    async def test_uses_explicit_bucket(self, mocker, connected_storage, s3_client):
        paginator = _paginator(mocker, s3_client, [])

        await connected_storage.get_bucket_size(bucket="other")

        paginator.paginate.assert_called_once_with(Bucket="other")

    async def test_returns_none_on_error(self, connected_storage, s3_client):
        s3_client.get_paginator.side_effect = _client_error("ListObjectsV2")

        assert await connected_storage.get_bucket_size() is None
