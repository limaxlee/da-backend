import asyncio
import logging
from contextlib import AsyncExitStack

import aiofiles
from aiobotocore.session import get_session
from botocore.exceptions import BotoCoreError, ClientError

from common.config import SETTINGS

logger = logging.getLogger(__name__)


class ObjectStorageClient:
    def __init__(self):
        self._client = None
        self._session = get_session()
        self._exit_stack = AsyncExitStack()
        self._lock = asyncio.Lock()
        self._config = {
            "bucket": SETTINGS.object_storage.bucket,
            "endpoint": SETTINGS.object_storage.endpoint,
            "access_key": SETTINGS.object_storage.access_key,
            "secret_key": SETTINGS.object_storage.secret_key
        }
        self._bucket = self._config["bucket"]

    @property
    def client(self):
        if self._client is None:
            raise RuntimeError("Object storage is not connected: connect() must run at application startup")
        return self._client

    async def connect(self) -> "ObjectStorageClient":
        if self._client is not None:
            return self

        async with self._lock:
            if self._client is not None:
                return self

            try:
                self._client = await self._exit_stack.enter_async_context(self._session.create_client(
                    "s3",
                    endpoint_url=self._config["endpoint"],
                    aws_access_key_id=self._config["access_key"],
                    aws_secret_access_key=self._config["secret_key"]
                ))
            except (BotoCoreError, ClientError):
                logger.exception("Failed to connect to object storage")
                await self._exit_stack.aclose()
                self._client = None
                raise
            except Exception:
                logger.exception("Unexpected error occurred during object storage connection")
                await self._exit_stack.aclose()
                self._client = None
                raise

        logger.info("Connected to object storage")
        return self

    async def disconnect(self) -> None:
        if self._client is None:
            return

        await self._exit_stack.aclose()
        self._client = None
        logger.info("Disconnected from object storage")

    async def __aenter__(self):
        return await self.connect()

    async def __aexit__(self, *exception_details):
        await self.disconnect()

    async def create_bucket(self, bucket: str = None) -> bool:
        bucket = bucket if bucket else self._bucket
        request_id = ""

        try:
            response = await self.client.create_bucket(Bucket=bucket)
            request_id = response.get("ResponseMetadata", {}).get("RequestId")

            logger.info(f"[{request_id}] Bucket '{bucket}' created successfully")
            return True
        except Exception as e:
            logger.exception(f"[{request_id}] Failed to create bucket '{bucket}': {e}")
            return False

    async def list_buckets(self) -> list[str] | None:
        request_id = ""

        try:
            response = await self.client.list_buckets()
            request_id = response.get("ResponseMetadata", {}).get("RequestId")
            buckets = [bucket["Name"] for bucket in response.get("Buckets", [])]
            return buckets
        except Exception as e:
            logger.exception(f"[{request_id}] Failed to list buckets: {e}")
            return None

    async def list_paginated_objects(
            self,
            prefix: str = "",
            max_items: int = 100,
            bucket: str = None) -> list[str] | None:
        bucket = bucket if bucket else self._bucket

        try:
            objects = []
            paginator = self.client.get_paginator("list_objects_v2")

            async for page in paginator.paginate(
                    Bucket=bucket,
                    Prefix=prefix,
                    PaginationConfig={"MaxItems": max_items}
            ):
                if page["KeyCount"] == 0:
                    continue

                for item in page["Contents"]:
                    objects.append(item["Key"])

            return objects
        except Exception as e:
            logger.exception(f"Failed to list objects in bucket '{bucket}': {e}")
            return None

    async def delete_bucket(self, bucket: str = None) -> bool:
        bucket = bucket if bucket else self._bucket
        request_id = ""

        try:
            response = await self.client.delete_bucket(Bucket=bucket)
            request_id = response.get("ResponseMetadata", {}).get("RequestId")
            logger.info(f"[{request_id}] Bucket '{bucket}' deleted successfully")
            return True
        except Exception as e:
            logger.exception(f"[{request_id}] Failed to delete bucket '{bucket}': {e}")
            return False

    async def upload_object(
            self,
            file_object: str | bytes,
            key: str, bucket: str = None,
            content_type: str | None = None
    ) -> bool:
        bucket = bucket if bucket else self._bucket
        request_id = ""

        try:
            if isinstance(file_object, str):
                async with aiofiles.open(file_object, "rb") as f:
                    data = await f.read()
            elif isinstance(file_object, bytes):
                data = file_object
            else:
                raise ValueError("Unsupported file type")

            extra_info = {"ContentType": content_type} if content_type else {}
            response = await self.client.put_object(Bucket=bucket, Body=data, Key=key, **extra_info)
            request_id = response.get("ResponseMetadata", {}).get("RequestId")

            logger.info(f"[{request_id}] Object uploaded to '{bucket}' as '{key}'")
            return True
        except Exception as e:
            logger.exception(f"[{request_id}] Failed to upload object '{key}': {e}")
            return False

    async def copy_object(self, destination_key: str, source_key: str, bucket: str = None) -> bool:
        bucket = bucket if bucket else self._bucket
        request_id = ""

        try:
            response = await self.client.copy_object(Bucket=bucket, Key=destination_key, CopySource={
                "Bucket": bucket,
                "Key": source_key
            })
            request_id = response.get("ResponseMetadata", {}).get("RequestId")
            logger.info(f"[{request_id}] Object copied to '{bucket}' from '{source_key}' to '{destination_key}'")
            return True
        except Exception as e:
            logger.exception(f"[{request_id}] Failed to copy object from '{source_key}' to '{destination_key}': {e}")
            return False

    async def retrieve_object(self, key: str, bucket: str = None) -> bytes | None:
        bucket = bucket if bucket else self._bucket
        request_id = ""

        try:
            response = await self.client.get_object(Bucket=bucket, Key=key)
            request_id = response.get("ResponseMetadata", {}).get("RequestId")

            async with response["Body"] as stream:
                data = await stream.read()

            logger.info(f"[{request_id}] Data retrieved from '{bucket}:{key}'")
            return data
        except Exception as e:
            logger.exception(f"[{request_id}] Failed to retrieve object '{key}' from bucket '{bucket}': {e}")
            return None

    async def retrieve_object_in_chunks(self, key: str, bucket: str = None):
        bucket = bucket if bucket else self._bucket
        request_id = ""

        try:
            response = await self.client.get_object(Bucket=bucket, Key=key)
            request_id = response.get("ResponseMetadata", {}).get("RequestId")
            body = response["Body"]

            async def get_chunks():
                async for chunk in body.iter_chunks(1024 * 1024):
                    if chunk:
                        yield chunk

            logger.info(f"[{request_id}] Data retrieved in chunks from '{bucket}:{key}'")
            return get_chunks()
        except Exception as e:
            logger.exception(f"[{request_id}] Failed to retrieve object '{key}' in chunks from bucket '{bucket}': {e}")

    async def retrieve_object_info(self, key: str, bucket: str = None) -> dict | None:
        bucket = bucket if bucket else self._bucket

        try:
            object_acl = await self.client.head_object(Bucket=bucket, Key=key)
            logger.info(f"ACL retrieved for '{bucket}:{key}'")
            return object_acl
        except Exception as e:
            logger.exception(f"Failed to retrieve ACL: {e}")
            return None

    async def delete_object(self, key: str, bucket: str = None) -> bool:
        bucket = bucket if bucket else self._bucket

        try:
            await self.client.delete_object(Bucket=bucket, Key=key)
            logger.info(f"Object '{key}' deleted from '{bucket}'")
            return True
        except Exception as e:
            logger.exception(f"Failed to delete object '{key}': {e}")
            return False

    async def delete_objects(self, keys: list[str], bucket: str = None) -> bool:
        bucket = bucket if bucket else self._bucket
        request_id = ""

        try:
            for i in range(0, len(keys), 1000):
                key_bulk = keys[i:i + 1000]
                response = await self.client.delete_objects(
                    Bucket=bucket, Delete={"Objects": [{"Key": key} for key in key_bulk]})
                request_id = response.get("ResponseMetadata", {}).get("RequestId")
                deleted_keys = [obj["Key"] for obj in response.get("Deleted", [])]
                logger.info(f"[{request_id}] Deleted objects: {deleted_keys} from '{bucket}'")
            return True
        except Exception as e:
            logger.exception(f"[{request_id}] Failed to delete objects: {e}")
            return False

    async def get_bucket_size(self, bucket: str = None) -> int | None:
        bucket = bucket if bucket else self._bucket

        try:
            total_size = 0
            paginator = self.client.get_paginator("list_objects_v2")
            pages = paginator.paginate(Bucket=bucket)

            async for page in pages:
                if "Contents" in page:
                    for obj in page["Contents"]:
                        total_size += obj["Size"]

            return total_size
        except Exception as e:
            logger.exception(f"Failed to get bucket size for '{bucket}': {e}")
            return None
