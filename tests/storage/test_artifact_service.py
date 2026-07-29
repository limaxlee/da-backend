import pytest

from data_agent.storage.artifact_service import ObjectStorageArtifactService

APP_NAME = "data_agent"
USER_ID = "user-1"
SESSION_ID = "session-1"
FILENAME = "chart.png"
USER_FILENAME = "user:profile.png"


@pytest.fixture
def storage(mocker):
    return mocker.AsyncMock()


@pytest.fixture
def service(storage):
    return ObjectStorageArtifactService(storage)


@pytest.fixture
def artifact(mocker):
    part = mocker.MagicMock()
    part.inline_data.data = b"payload"
    part.inline_data.mime_type = "image/png"
    return part


@pytest.fixture
def mock_types(mocker):
    return mocker.patch("data_agent.storage.artifact_service.types")


class TestKeyBuilding:

    def test_has_user_namespace_detects_user_prefix(self):
        assert ObjectStorageArtifactService._has_user_namespace(USER_FILENAME) is True

    def test_has_user_namespace_is_false_for_session_scoped_file(self):
        assert ObjectStorageArtifactService._has_user_namespace(FILENAME) is False

    def test_session_scoped_prefix(self, service):
        prefix = service.get_object_prefix(APP_NAME, USER_ID, SESSION_ID, FILENAME)

        assert prefix == f"{APP_NAME}/{USER_ID}/{SESSION_ID}/{FILENAME}"

    def test_user_scoped_prefix_ignores_session(self, service):
        prefix = service.get_object_prefix(APP_NAME, USER_ID, SESSION_ID, USER_FILENAME)

        assert prefix == f"{APP_NAME}/{USER_ID}/user/{USER_FILENAME}"

    def test_object_key_appends_version(self, service):
        key = service.get_object_key(APP_NAME, USER_ID, SESSION_ID, FILENAME, 3)

        assert key == f"{APP_NAME}/{USER_ID}/{SESSION_ID}/{FILENAME}/3"

    def test_object_key_for_user_scoped_file(self, service):
        key = service.get_object_key(APP_NAME, USER_ID, SESSION_ID, USER_FILENAME, 0)

        assert key == f"{APP_NAME}/{USER_ID}/user/{USER_FILENAME}/0"

    def test_missing_session_id_becomes_part_of_the_key(self, service):
        prefix = service.get_object_prefix(APP_NAME, USER_ID, None, FILENAME)

        assert prefix == f"{APP_NAME}/{USER_ID}/None/{FILENAME}"


class TestListVersions:
    pytestmark = pytest.mark.asyncio

    async def test_returns_sorted_versions(self, service, storage):
        prefix = f"{APP_NAME}/{USER_ID}/{SESSION_ID}/{FILENAME}/"
        storage.list_paginated_objects.return_value = [
            f"{prefix}2", f"{prefix}0", f"{prefix}1"
        ]

        versions = await service.list_versions(
            app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID, filename=FILENAME
        )

        assert versions == [0, 1, 2]
        storage.list_paginated_objects.assert_awaited_once_with(
            prefix=prefix, max_items=100_000
        )

    async def test_queries_user_namespace_prefix(self, service, storage):
        storage.list_paginated_objects.return_value = []

        await service.list_versions(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=SESSION_ID,
            filename=USER_FILENAME,
        )

        storage.list_paginated_objects.assert_awaited_once_with(
            prefix=f"{APP_NAME}/{USER_ID}/user/{USER_FILENAME}/", max_items=100_000
        )

    async def test_skips_non_numeric_suffixes(self, service, storage):
        prefix = f"{APP_NAME}/{USER_ID}/{SESSION_ID}/{FILENAME}/"
        storage.list_paginated_objects.return_value = [
            f"{prefix}0", f"{prefix}latest", f"{prefix}1"
        ]

        versions = await service.list_versions(
            app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID, filename=FILENAME
        )

        assert versions == [0, 1]

    async def test_returns_empty_list_when_nothing_stored(self, service, storage):
        storage.list_paginated_objects.return_value = []

        versions = await service.list_versions(
            app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID, filename=FILENAME
        )

        assert versions == []

    async def test_returns_empty_list_when_storage_fails(self, service, storage):
        storage.list_paginated_objects.return_value = None

        versions = await service.list_versions(
            app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID, filename=FILENAME
        )

        assert versions == []


class TestSaveArtifact:
    pytestmark = pytest.mark.asyncio

    async def test_first_version_is_zero(self, mocker, service, storage, artifact):
        mocker.patch.object(service, "list_versions", new=mocker.AsyncMock(return_value=[]))
        storage.upload_object.return_value = True

        version = await service.save_artifact(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=SESSION_ID,
            filename=FILENAME,
            artifact=artifact,
        )

        assert version == 0
        storage.upload_object.assert_awaited_once_with(
            file_object=b"payload",
            key=f"{APP_NAME}/{USER_ID}/{SESSION_ID}/{FILENAME}/0",
            content_type="image/png",
        )

    async def test_increments_past_highest_existing_version(
        self, mocker, service, storage, artifact
    ):
        mocker.patch.object(
            service, "list_versions", new=mocker.AsyncMock(return_value=[0, 1, 4])
        )
        storage.upload_object.return_value = True

        version = await service.save_artifact(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=SESSION_ID,
            filename=FILENAME,
            artifact=artifact,
        )

        assert version == 5
        assert storage.upload_object.await_args.kwargs["key"].endswith("/5")

    async def test_stores_user_scoped_artifact_under_user_prefix(
        self, mocker, service, storage, artifact
    ):
        mocker.patch.object(service, "list_versions", new=mocker.AsyncMock(return_value=[]))
        storage.upload_object.return_value = True

        await service.save_artifact(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=SESSION_ID,
            filename=USER_FILENAME,
            artifact=artifact,
        )

        assert storage.upload_object.await_args.kwargs["key"] == (
            f"{APP_NAME}/{USER_ID}/user/{USER_FILENAME}/0"
        )

    async def test_looks_up_versions_for_the_same_artifact(
        self, mocker, service, storage, artifact
    ):
        mock_list_versions = mocker.patch.object(
            service, "list_versions", new=mocker.AsyncMock(return_value=[])
        )
        storage.upload_object.return_value = True

        await service.save_artifact(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=SESSION_ID,
            filename=FILENAME,
            artifact=artifact,
        )

        mock_list_versions.assert_awaited_once_with(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=SESSION_ID,
            filename=FILENAME,
        )

    async def test_raises_when_artifact_has_no_inline_data(
        self, mocker, service, storage, artifact
    ):
        mocker.patch.object(service, "list_versions", new=mocker.AsyncMock(return_value=[]))
        artifact.inline_data = None

        with pytest.raises(ValueError, match="no inline_data"):
            await service.save_artifact(
                app_name=APP_NAME,
                user_id=USER_ID,
                session_id=SESSION_ID,
                filename=FILENAME,
                artifact=artifact,
            )

        storage.upload_object.assert_not_awaited()

    async def test_raises_when_upload_fails(self, mocker, service, storage, artifact):
        mocker.patch.object(service, "list_versions", new=mocker.AsyncMock(return_value=[]))
        storage.upload_object.return_value = False

        with pytest.raises(RuntimeError, match="Failed to upload artifact"):
            await service.save_artifact(
                app_name=APP_NAME,
                user_id=USER_ID,
                session_id=SESSION_ID,
                filename=FILENAME,
                artifact=artifact,
            )


class TestLoadArtifact:
    pytestmark = pytest.mark.asyncio

    async def test_loads_requested_version(
        self, mocker, service, storage, mock_types
    ):
        storage.retrieve_object.return_value = b"payload"
        storage.retrieve_object_info.return_value = {"ContentType": "image/png"}

        result = await service.load_artifact(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=SESSION_ID,
            filename=FILENAME,
            version=2,
        )

        key = f"{APP_NAME}/{USER_ID}/{SESSION_ID}/{FILENAME}/2"
        storage.retrieve_object.assert_awaited_once_with(key=key)
        storage.retrieve_object_info.assert_awaited_once_with(key=key)
        mock_types.Part.from_bytes.assert_called_once_with(
            data=b"payload", mime_type="image/png"
        )
        assert result is mock_types.Part.from_bytes.return_value

    async def test_does_not_list_versions_when_version_given(
        self, mocker, service, storage, mock_types
    ):
        mock_list_versions = mocker.patch.object(
            service, "list_versions", new=mocker.AsyncMock()
        )
        storage.retrieve_object.return_value = b"payload"
        storage.retrieve_object_info.return_value = {}

        await service.load_artifact(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=SESSION_ID,
            filename=FILENAME,
            version=0,
        )

        mock_list_versions.assert_not_awaited()

    async def test_loads_latest_version_by_default(
        self, mocker, service, storage, mock_types
    ):
        mocker.patch.object(
            service, "list_versions", new=mocker.AsyncMock(return_value=[0, 1, 2])
        )
        storage.retrieve_object.return_value = b"payload"
        storage.retrieve_object_info.return_value = {"ContentType": "image/png"}

        await service.load_artifact(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=SESSION_ID,
            filename=FILENAME,
        )

        storage.retrieve_object.assert_awaited_once_with(
            key=f"{APP_NAME}/{USER_ID}/{SESSION_ID}/{FILENAME}/2"
        )

    async def test_returns_none_when_no_versions_exist(
        self, mocker, service, storage, mock_types
    ):
        mocker.patch.object(service, "list_versions", new=mocker.AsyncMock(return_value=[]))

        result = await service.load_artifact(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=SESSION_ID,
            filename=FILENAME,
        )

        assert result is None
        storage.retrieve_object.assert_not_awaited()

    async def test_returns_none_when_object_is_missing(
        self, service, storage, mock_types
    ):
        storage.retrieve_object.return_value = None

        result = await service.load_artifact(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=SESSION_ID,
            filename=FILENAME,
            version=0,
        )

        assert result is None
        storage.retrieve_object_info.assert_not_awaited()

    async def test_falls_back_to_octet_stream_when_info_is_missing(
        self, service, storage, mock_types
    ):
        storage.retrieve_object.return_value = b"payload"
        storage.retrieve_object_info.return_value = None

        await service.load_artifact(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=SESSION_ID,
            filename=FILENAME,
            version=0,
        )

        mock_types.Part.from_bytes.assert_called_once_with(
            data=b"payload", mime_type="application/octet-stream"
        )

    async def test_falls_back_to_octet_stream_when_content_type_is_empty(
        self, service, storage, mock_types
    ):
        storage.retrieve_object.return_value = b"payload"
        storage.retrieve_object_info.return_value = {"ContentType": ""}

        await service.load_artifact(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=SESSION_ID,
            filename=FILENAME,
            version=0,
        )

        mock_types.Part.from_bytes.assert_called_once_with(
            data=b"payload", mime_type="application/octet-stream"
        )

    async def test_loads_user_scoped_artifact(self, service, storage, mock_types):
        storage.retrieve_object.return_value = b"payload"
        storage.retrieve_object_info.return_value = {"ContentType": "image/png"}

        await service.load_artifact(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=SESSION_ID,
            filename=USER_FILENAME,
            version=1,
        )

        storage.retrieve_object.assert_awaited_once_with(
            key=f"{APP_NAME}/{USER_ID}/user/{USER_FILENAME}/1"
        )


class TestListArtifactKeys:
    pytestmark = pytest.mark.asyncio

    async def test_queries_session_and_user_prefixes(self, service, storage):
        storage.list_paginated_objects.return_value = []

        await service.list_artifact_keys(
            app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
        )

        prefixes = [
            call.kwargs["prefix"]
            for call in storage.list_paginated_objects.await_args_list
        ]
        assert prefixes == [
            f"{APP_NAME}/{USER_ID}/{SESSION_ID}/",
            f"{APP_NAME}/{USER_ID}/user/",
        ]

    async def test_returns_sorted_unique_filenames(self, service, storage):
        session_prefix = f"{APP_NAME}/{USER_ID}/{SESSION_ID}/"
        user_prefix = f"{APP_NAME}/{USER_ID}/user/"
        storage.list_paginated_objects.side_effect = [
            [f"{session_prefix}b.png/0", f"{session_prefix}a.png/0",
             f"{session_prefix}a.png/1"],
            [f"{user_prefix}user:c.png/0"],
        ]

        keys = await service.list_artifact_keys(
            app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
        )

        assert keys == ["a.png", "b.png", "user:c.png"]

    async def test_skips_keys_without_a_version_segment(self, service, storage):
        session_prefix = f"{APP_NAME}/{USER_ID}/{SESSION_ID}/"
        storage.list_paginated_objects.side_effect = [
            [f"{session_prefix}orphan", f"{session_prefix}a.png/0"],
            [],
        ]

        keys = await service.list_artifact_keys(
            app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
        )

        assert keys == ["a.png"]

    async def test_keeps_nested_filenames_intact(self, service, storage):
        session_prefix = f"{APP_NAME}/{USER_ID}/{SESSION_ID}/"
        storage.list_paginated_objects.side_effect = [
            [f"{session_prefix}reports/q1.csv/0"],
            [],
        ]

        keys = await service.list_artifact_keys(
            app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
        )

        assert keys == ["reports/q1.csv"]

    async def test_returns_empty_list_when_storage_fails(self, service, storage):
        storage.list_paginated_objects.return_value = None

        keys = await service.list_artifact_keys(
            app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID
        )

        assert keys == []


class TestDeleteArtifact:
    pytestmark = pytest.mark.asyncio

    async def test_deletes_every_version(self, mocker, service, storage):
        mocker.patch.object(
            service, "list_versions", new=mocker.AsyncMock(return_value=[0, 1])
        )

        await service.delete_artifact(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=SESSION_ID,
            filename=FILENAME,
        )

        prefix = f"{APP_NAME}/{USER_ID}/{SESSION_ID}/{FILENAME}"
        storage.delete_objects.assert_awaited_once_with(
            keys=[f"{prefix}/0", f"{prefix}/1"]
        )

    async def test_deletes_user_scoped_versions(self, mocker, service, storage):
        mocker.patch.object(
            service, "list_versions", new=mocker.AsyncMock(return_value=[0])
        )

        await service.delete_artifact(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=SESSION_ID,
            filename=USER_FILENAME,
        )

        storage.delete_objects.assert_awaited_once_with(
            keys=[f"{APP_NAME}/{USER_ID}/user/{USER_FILENAME}/0"]
        )

    async def test_does_nothing_when_artifact_is_absent(
        self, mocker, service, storage
    ):
        mocker.patch.object(service, "list_versions", new=mocker.AsyncMock(return_value=[]))

        await service.delete_artifact(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=SESSION_ID,
            filename=FILENAME,
        )

        storage.delete_objects.assert_not_awaited()

    async def test_returns_none(self, mocker, service, storage):
        mocker.patch.object(
            service, "list_versions", new=mocker.AsyncMock(return_value=[0])
        )

        result = await service.delete_artifact(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=SESSION_ID,
            filename=FILENAME,
        )

        assert result is None


class TestUnimplementedApi:
    pytestmark = pytest.mark.asyncio

    async def test_list_artifact_versions_returns_none(self, service):
        result = await service.list_artifact_versions(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=SESSION_ID,
            filename=FILENAME,
        )

        assert result is None

    async def test_get_artifact_version_returns_none(self, service):
        result = await service.get_artifact_version(
            app_name=APP_NAME,
            user_id=USER_ID,
            session_id=SESSION_ID,
            filename=FILENAME,
            version=0,
        )

        assert result is None
