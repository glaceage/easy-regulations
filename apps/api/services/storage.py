import hashlib
import uuid

import boto3
from botocore.exceptions import ClientError

from apps.api.config import Settings, get_settings


class StorageService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._last_sha256 = ""
        self._client = boto3.client(
            "s3",
            endpoint_url=self._settings.minio_endpoint,
            aws_access_key_id=self._settings.minio_access_key,
            aws_secret_access_key=self._settings.minio_secret_key,
            region_name=self._settings.minio_region,
        )
        self._ensure_bucket()

    @property
    def last_sha256(self) -> str:
        return self._last_sha256

    def _ensure_bucket(self) -> None:
        bucket = self._settings.minio_bucket
        try:
            self._client.head_bucket(Bucket=bucket)
        except ClientError:
            self._client.create_bucket(Bucket=bucket)

    def put_bytes(self, data: bytes, suffix: str, prefix: str = "") -> str:
        content_sha256 = hashlib.sha256(data).hexdigest()
        self._last_sha256 = content_sha256
        key = f"{prefix}{uuid.uuid4()}{suffix}"
        self._client.put_object(
            Bucket=self._settings.minio_bucket,
            Key=key,
            Body=data,
            Metadata={"content-sha256": content_sha256},
        )
        return key

    def put_object(self, key: str, data: bytes) -> str:
        """Write ``data`` to a caller-provided key, overwriting in place.

        Used for mutable objects (e.g. the working draft markdown) that must keep
        a stable key across edits, unlike ``put_bytes`` which mints a new key.
        """
        content_sha256 = hashlib.sha256(data).hexdigest()
        self._last_sha256 = content_sha256
        self._client.put_object(
            Bucket=self._settings.minio_bucket,
            Key=key,
            Body=data,
            Metadata={"content-sha256": content_sha256},
        )
        return key

    def get_bytes(self, key: str) -> bytes:
        response = self._client.get_object(
            Bucket=self._settings.minio_bucket,
            Key=key,
        )
        return response["Body"].read()
