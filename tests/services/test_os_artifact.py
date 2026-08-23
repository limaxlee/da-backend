from types import SimpleNamespace

import pytest

from data_agent.services.os_artifact import OSArtifactService


@pytest.fixture
def storage(mocker):
    return mocker.Mock(
        upload_object=mocker.AsyncMock(),
        retrieve_object=mocker.AsyncMock(),
        retrieve_object_info=mocker.AsyncMock(),
        list_paginated_objects=mocker.AsyncMock(),
        delete_objects=mocker.AsyncMock(),
    )


@pytest.fixture
def service(storage):
    return OSArtifactService(storage=storage)


def _artifact(data=b"payload", mime_type="image/png"):
    return SimpleNamespace(inline_data=SimpleNamespace(data=data, mime_type=mime_type))


class TestOSArtifactService:
    def test__has_user_namespace(self, service):
        assert service._has_user_namespace("user:notes.txt") is True
        assert service._has_user_namespace("notes.txt") is False

    def test_get_object_prefix(self, service):
        assert service.get_object_prefix("app", "u1", "s1", "notes.txt") == "app/u1/s1/notes.txt"
        assert service.get_object_prefix("app", "u1", "s1", "user:notes.txt") == "app/u1/user/user:notes.txt"

    def test_get_object_key(self, service):
        assert service.get_object_key("app", "u1", "s1", "notes.txt", 3) == "app/u1/s1/notes.txt/3"

    @pytest.mark.asyncio
    async def test_save_artifact(self, mocker, service, storage):
        mocker.patch.object(service, "list_versions", mocker.AsyncMock(return_value=[0, 1]))
        storage.upload_object.return_value = True

        version = await service.save_artifact(
            app_name="app", user_id="u1", session_id="s1", filename="img.png", artifact=_artifact()
        )

        assert version == 2
        storage.upload_object.assert_awaited_once_with(
            file_object=b"payload", key="app/u1/s1/img.png/2", content_type="image/png"
        )

        with pytest.raises(ValueError):
            await service.save_artifact(
                app_name="app", user_id="u1", session_id="s1", filename="img.png",
                artifact=SimpleNamespace(inline_data=None),
            )

        storage.upload_object.return_value = False
        with pytest.raises(RuntimeError):
            await service.save_artifact(
                app_name="app", user_id="u1", session_id="s1", filename="img.png", artifact=_artifact()
            )

    @pytest.mark.asyncio
    async def test_load_artifact(self, mocker, service, storage):
        list_versions = mocker.patch.object(service, "list_versions", mocker.AsyncMock(return_value=[0, 3]))
        storage.retrieve_object.return_value = b"payload"
        storage.retrieve_object_info.return_value = {"ContentType": "image/png"}

        part = await service.load_artifact(app_name="app", user_id="u1", session_id="s1", filename="img.png")

        assert part.inline_data.data == b"payload"
        assert part.inline_data.mime_type == "image/png"
        storage.retrieve_object.assert_awaited_once_with(key="app/u1/s1/img.png/3")

        storage.retrieve_object.return_value = None
        assert await service.load_artifact(
            app_name="app", user_id="u1", session_id="s1", filename="img.png", version=1
        ) is None

        list_versions.return_value = []
        assert await service.load_artifact(
            app_name="app", user_id="u1", session_id="s1", filename="img.png"
        ) is None

    @pytest.mark.asyncio
    async def test_list_artifact_keys(self, service, storage):
        storage.list_paginated_objects.side_effect = [
            ["app/u1/s1/report.csv/0", "app/u1/s1/report.csv/1", "app/u1/s1/orphan"],
            ["app/u1/user/user:notes.txt/0"],
        ]

        filenames = await service.list_artifact_keys(app_name="app", user_id="u1", session_id="s1")

        assert filenames == sorted(["report.csv", "user:notes.txt"])
        prefixes = [call.kwargs["prefix"] for call in storage.list_paginated_objects.await_args_list]
        assert prefixes == ["app/u1/s1/", "app/u1/user/"]

    @pytest.mark.asyncio
    async def test_list_versions(self, service, storage):
        storage.list_paginated_objects.return_value = [
            "app/u1/s1/img.png/2",
            "app/u1/s1/img.png/0",
            "app/u1/s1/img.png/not-a-version",
        ]

        versions = await service.list_versions(app_name="app", user_id="u1", session_id="s1", filename="img.png")

        assert versions == [0, 2]
        storage.list_paginated_objects.assert_awaited_once_with(prefix="app/u1/s1/img.png/", max_items=100_000)

    @pytest.mark.asyncio
    async def test_delete_artifact(self, mocker, service, storage):
        list_versions = mocker.patch.object(service, "list_versions", mocker.AsyncMock(return_value=[0, 1]))

        await service.delete_artifact(app_name="app", user_id="u1", session_id="s1", filename="img.png")
        storage.delete_objects.assert_awaited_once_with(
            keys=["app/u1/s1/img.png/0", "app/u1/s1/img.png/1"]
        )

        storage.delete_objects.reset_mock()
        list_versions.return_value = []
        await service.delete_artifact(app_name="app", user_id="u1", session_id="s1", filename="img.png")
        storage.delete_objects.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_list_artifact_versions(self, service):
        assert await service.list_artifact_versions(app_name="app", user_id="u1", filename="img.png") is None

    @pytest.mark.asyncio
    async def test_get_artifact_version(self, service):
        assert await service.get_artifact_version(app_name="app", user_id="u1", filename="img.png") is None
