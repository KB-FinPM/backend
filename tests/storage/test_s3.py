import pytest

from app.storage.s3 import S3Service


@pytest.mark.anyio
async def test_s3_service_uses_mock_backend_by_default(monkeypatch) -> None:
    monkeypatch.setattr("app.storage.s3.settings.S3_STORAGE_BACKEND", "mock")
    monkeypatch.setattr("app.storage.s3.settings.S3_BUCKET_NAME", "test-bucket")

    service = S3Service()
    storage_path = await service.upload(b"hello", "path/file.txt")
    url = await service.get_presigned_url("path/file.txt")

    assert service.client is None
    assert storage_path == "s3://test-bucket/path/file.txt"
    assert url == "https://mock-presigned-url/path/file.txt"


def test_s3_service_initializes_boto3_client_for_s3_backend(monkeypatch) -> None:
    received: dict = {}

    def fake_client(service_name: str, region_name: str, verify):
        received["service_name"] = service_name
        received["region_name"] = region_name
        received["verify"] = verify
        return object()

    monkeypatch.setattr("app.storage.s3.settings.S3_STORAGE_BACKEND", "s3")
    monkeypatch.setattr("app.storage.s3.settings.AWS_REGION", "ap-northeast-2")
    monkeypatch.setattr("app.storage.s3.settings.AWS_CA_BUNDLE", "")
    monkeypatch.setattr("app.storage.s3.settings.AWS_VERIFY_SSL", True)
    monkeypatch.setattr("app.storage.s3.boto3.client", fake_client)

    service = S3Service()

    assert service.client is not None
    assert received == {
        "service_name": "s3",
        "region_name": "ap-northeast-2",
        "verify": True,
    }


def test_s3_service_uses_ca_bundle_for_ssl_verification(monkeypatch) -> None:
    received: dict = {}

    def fake_client(service_name: str, region_name: str, verify):
        received["verify"] = verify
        return object()

    monkeypatch.setattr("app.storage.s3.settings.S3_STORAGE_BACKEND", "s3")
    monkeypatch.setattr("app.storage.s3.settings.AWS_CA_BUNDLE", "C:/certs/ca.pem")
    monkeypatch.setattr("app.storage.s3.boto3.client", fake_client)

    S3Service()

    assert received["verify"] == "C:/certs/ca.pem"
