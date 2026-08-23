import logging
from typing import Optional, Union, Any
from google.adk.artifacts import BaseArtifactService
from google.genai import types

from data_agent.storage import ObjectStorage

logger = logging.getLogger(__name__)


class OSArtifactService(BaseArtifactService):
    def __init__(self, storage: ObjectStorage):
        self._storage = storage

    @staticmethod
    def _has_user_namespace(filename: str) -> bool:
        return filename.startswith("user:")

    def get_object_prefix(self, app_name: str, user_id: str, session_id: str, filename: str) -> str:
        if self._has_user_namespace(filename):
            return f"{app_name}/{user_id}/user/{filename}"
        return f"{app_name}/{user_id}/{session_id}/{filename}"

    def get_object_key(self, app_name: str, user_id: str, session_id: str, filename: str, version: int) -> str:
        return f"{self.get_object_prefix(app_name, user_id, session_id, filename)}/{version}"

    async def save_artifact(
            self,
            *,
            app_name: str,
            user_id: str,
            filename: str,
            artifact: Union[types.Part, dict[str, Any]],
            session_id: Optional[str] = None,
            custom_metadata: Optional[dict[str, Any]] = None,
    ) -> int:
        storage = self._storage

        versions = await self.list_versions(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
            filename=filename
        )
        version = 0 if not versions else max(versions) + 1

        key = self.get_object_key(app_name, user_id, session_id, filename, version)

        if artifact.inline_data is None:
            raise ValueError(f"Artifact '{filename}' has no inline_data to store")

        response = await storage.upload_object(
            file_object=artifact.inline_data.data,
            key=key,
            content_type=artifact.inline_data.mime_type
        )
        if not response:
            raise RuntimeError(f"Failed to upload artifact '{filename}' (key='{key}')")

        logger.info(f"Saved artifact '{filename}' v{version} at '{key}'")
        return version

    async def load_artifact(
            self,
            *,
            app_name: str,
            user_id: str,
            filename: str,
            session_id: Optional[str] = None,
            version: Optional[int] = None
    ) -> Optional[types.Part]:
        storage = self._storage

        if version is None:
            versions = await self.list_versions(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id,
                filename=filename
            )
            if not versions:
                return None
            version = max(versions)

        key = self.get_object_key(app_name, user_id, session_id, filename, version)
        data = await storage.retrieve_object(key=key)
        if data is None:
            return None

        info = await storage.retrieve_object_info(key=key)
        mime_type = (info or {}).get("ContentType") or "application/octet-stream"

        return types.Part.from_bytes(data=data, mime_type=mime_type)

    async def list_artifact_keys(self, *, app_name: str, user_id: str, session_id: Optional[str] = None) -> list[str]:
        storage = self._storage
        filenames = set()
        session_prefix = f"{app_name}/{user_id}/{session_id}/"
        user_prefix = f"{app_name}/{user_id}/user/"

        for prefix in (session_prefix, user_prefix):
            keys = await storage.list_paginated_objects(prefix=prefix, max_items=100_000) or []
            for key in keys:
                rest = key[len(prefix):]
                if "/" not in rest:
                    continue
                filename, _version = rest.rsplit("/", 1)
                filenames.add(filename)

        return sorted(filenames)

    async def list_versions(
            self,
            *,
            app_name: str,
            user_id: str,
            filename: str,
            session_id: Optional[str] = None
    ) -> list[int]:
        storage = self._storage
        prefix = self.get_object_prefix(app_name, user_id, session_id, filename) + "/"
        keys = await storage.list_paginated_objects(prefix=prefix, max_items=100_000) or []
        versions = []

        for key in keys:
            suffix = key[len(prefix):]
            try:
                versions.append(int(suffix))
            except ValueError:
                continue
        return sorted(versions)

    async def delete_artifact(
            self,
            *,
            app_name: str,
            user_id: str,
            filename: str,
            session_id: Optional[str] = None
    ) -> None:
        storage = self._storage
        versions = await self.list_versions(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
            filename=filename
        )
        if not versions:
            return

        keys = [
            self.get_object_key(app_name, user_id, session_id, filename, version)
            for version in versions
        ]
        await storage.delete_objects(keys=keys)
        logger.info(f"Deleted artifact '{filename}' ({len(keys)} version(s))")

    async def list_artifact_versions(
            self,
            *,
            app_name: str,
            user_id: str,
            filename: str,
            session_id: Optional[str] = None,
    ):
        ...

    async def get_artifact_version(
            self,
            *,
            app_name: str,
            user_id: str,
            filename: str,
            session_id: Optional[str] = None,
            version: Optional[int] = None,
    ):
        ...
