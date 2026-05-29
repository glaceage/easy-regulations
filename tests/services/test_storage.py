import hashlib
import re
import uuid
from unittest.mock import MagicMock, patch

from botocore.exceptions import ClientError

from apps.api.services.storage import StorageService


def _mock_s3_client(*, bucket_exists: bool = False):
    s3 = MagicMock()
    store: dict[str, bytes] = {}

    def put_object(**kwargs):
        store[kwargs["Key"]] = kwargs["Body"]

    def get_object(**kwargs):
        return {"Body": MagicMock(read=lambda: store[kwargs["Key"]])}

    s3.put_object.side_effect = put_object
    s3.get_object.side_effect = get_object
    if bucket_exists:
        s3.head_bucket.return_value = {}
    else:
        s3.head_bucket.side_effect = ClientError({"Error": {"Code": "404"}}, "HeadBucket")
    return s3, store


def test_put_and_get_roundtrip():
    with patch("apps.api.services.storage.boto3.client") as mock_client:
        s3, _store = _mock_s3_client()
        mock_client.return_value = s3
        svc = StorageService()
        key = svc.put_bytes(b"# md", suffix=".md")
        assert svc.get_bytes(key) == b"# md"


def test_put_bytes_computes_sha256():
    data = b"# policy draft"
    expected = hashlib.sha256(data).hexdigest()
    with patch("apps.api.services.storage.boto3.client") as mock_client:
        s3, _store = _mock_s3_client()
        mock_client.return_value = s3
        svc = StorageService()
        svc.put_bytes(data, suffix=".md")
        assert svc.last_sha256 == expected


def test_put_bytes_stores_sha256_metadata():
    data = b"content"
    expected = hashlib.sha256(data).hexdigest()
    with patch("apps.api.services.storage.boto3.client") as mock_client:
        s3, _store = _mock_s3_client()
        mock_client.return_value = s3
        svc = StorageService()
        svc.put_bytes(data, suffix=".md")
        _, kwargs = s3.put_object.call_args
        assert kwargs["Metadata"]["content-sha256"] == expected


def test_simple_uuid_key_without_prefix():
    with patch("apps.api.services.storage.boto3.client") as mock_client:
        s3, _store = _mock_s3_client()
        mock_client.return_value = s3
        svc = StorageService()
        key = svc.put_bytes(b"x", suffix=".pdf")
        assert re.fullmatch(r"[0-9a-f-]{36}\.pdf", key)


def test_policy_revision_key_naming():
    policy_id = uuid.uuid4()
    revision_id = uuid.uuid4()
    prefix = f"policies/{policy_id}/{revision_id}/"
    with patch("apps.api.services.storage.boto3.client") as mock_client:
        s3, _store = _mock_s3_client()
        mock_client.return_value = s3
        svc = StorageService()
        key = svc.put_bytes(b"x", suffix=".md", prefix=prefix)
        pattern = rf"policies/{policy_id}/{revision_id}/[0-9a-f-]{{36}}\.md"
        assert re.fullmatch(pattern, key)


def test_ensure_bucket_creates_when_missing():
    with patch("apps.api.services.storage.boto3.client") as mock_client:
        s3, _store = _mock_s3_client()
        mock_client.return_value = s3
        StorageService()
        s3.create_bucket.assert_called_once()


def test_ensure_bucket_skips_create_when_exists():
    with patch("apps.api.services.storage.boto3.client") as mock_client:
        s3, _store = _mock_s3_client(bucket_exists=True)
        mock_client.return_value = s3
        StorageService()
        s3.head_bucket.assert_called_once()
        s3.create_bucket.assert_not_called()
