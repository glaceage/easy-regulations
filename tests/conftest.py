from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError


@pytest.fixture(autouse=True)
def mock_storage_service():
    """API tests run without MinIO; stub object storage writes/reads."""
    storage = MagicMock()
    _store: dict[str, bytes] = {}

    def put_object(key: str, data: bytes) -> str:
        _store[key] = data
        return key

    def put_bytes(data: bytes, suffix: str, prefix: str = "") -> str:
        import uuid

        key = f"{prefix}{uuid.uuid4()}{suffix}"
        _store[key] = data
        return key

    def get_bytes(key: str) -> bytes:
        if key not in _store:
            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return _store[key]

    storage.put_object.side_effect = put_object
    storage.put_bytes.side_effect = put_bytes
    storage.get_bytes.side_effect = get_bytes
    storage.last_sha256 = "abc123"

    with patch("apps.api.services.revisions.StorageService", return_value=storage):
        with patch("apps.api.services.ai.StorageService", return_value=storage):
            yield storage
