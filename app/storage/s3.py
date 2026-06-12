# EN: S3 storage service wrapper for document and artifact files.
# KO: 문서와 산출물 파일을 다루는 S3 저장소 서비스 래퍼입니다.

import asyncio
from pathlib import Path
from urllib.parse import urlparse

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import BASE_DIR, settings
from app.core.logger import get_logger

logger = get_logger(__name__)
_mock_storage: dict[str, tuple[bytes, str | None]] = {}
_mock_content_types: dict[str, str | None] = {}
_mock_storage_root = BASE_DIR / ".mock_s3"


class S3Service:
    """Handles file upload and lookup through mock or real S3 storage."""

    def __init__(self) -> None:
        self.bucket = settings.S3_BUCKET_NAME
        self.backend = settings.S3_STORAGE_BACKEND.lower()
        self.client = None
        if self.backend == "s3":
            self.client = boto3.client(
                "s3",
                region_name=settings.AWS_REGION,
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
                verify=self._ssl_verify_setting(),
            )

    def _ssl_verify_setting(self) -> bool | str:
        if settings.AWS_CA_BUNDLE:
            return settings.AWS_CA_BUNDLE

        return settings.AWS_VERIFY_SSL

    async def upload(self, file_bytes: bytes, key: str, content_type: str | None = None) -> str:
        logger.info(f"[S3] upload | backend={self.backend} | bucket={self.bucket} | key={key}")
        if self.client is None:
            _mock_storage[key] = (file_bytes, content_type)
            _mock_content_types[key] = content_type
            mock_path = self._mock_object_path(key)
            await asyncio.to_thread(mock_path.parent.mkdir, parents=True, exist_ok=True)
            await asyncio.to_thread(mock_path.write_bytes, file_bytes)
            return f"s3://{self.bucket}/{key}"

        try:
            await asyncio.to_thread(
                self.client.put_object,
                Bucket=self.bucket,
                Key=key,
                Body=file_bytes,
                **({"ContentType": content_type} if content_type else {}),
            )
        except (BotoCoreError, ClientError) as exc:
            logger.exception("S3 upload failed")
            raise RuntimeError(f"S3 upload failed: {type(exc).__name__}: {exc}") from exc

        return f"s3://{self.bucket}/{key}"

    async def download_by_storage_path(self, storage_path: str) -> tuple[bytes, str | None]:
        key = self._key_from_storage_path(storage_path)
        logger.info(f"[S3] download | backend={self.backend} | bucket={self.bucket} | key={key}")
        if self.client is None:
            if key in _mock_storage:
                return _mock_storage[key]
            mock_path = self._mock_object_path(key)
            if not mock_path.exists():
                raise FileNotFoundError(f"mock object not found: {key}")
            file_bytes = await asyncio.to_thread(mock_path.read_bytes)
            return file_bytes, _mock_content_types.get(key)

        try:
            response = await asyncio.to_thread(
                self.client.get_object,
                Bucket=self.bucket,
                Key=key,
            )
            body = await asyncio.to_thread(response["Body"].read)
            return body, response.get("ContentType")
        except ClientError as exc:
            error_code = str((exc.response.get("Error") or {}).get("Code") or "")
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                raise FileNotFoundError(f"s3 object not found: {key}") from exc
            logger.exception("S3 download failed")
            raise RuntimeError(f"S3 download failed: {type(exc).__name__}: {exc}") from exc
        except BotoCoreError as exc:
            logger.exception("S3 download failed")
            raise RuntimeError(f"S3 download failed: {type(exc).__name__}: {exc}") from exc

    def _key_from_storage_path(self, storage_path: str) -> str:
        parsed = urlparse(storage_path)
        if parsed.scheme == "s3":
            return parsed.path.lstrip("/")
        return storage_path.lstrip("/")

    def _mock_object_path(self, key: str) -> Path:
        return _mock_storage_root / key

    async def get_presigned_url(self, key: str, expires: int = 3600) -> str:
        logger.info(f"[S3] presigned_url | backend={self.backend} | key={key}")
        if self.client is None:
            return f"https://mock-presigned-url/{key}"

        try:
            return await asyncio.to_thread(
                self.client.generate_presigned_url,
                ClientMethod="get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires,
            )
        except (BotoCoreError, ClientError) as exc:
            logger.exception("S3 presigned URL generation failed")
            raise RuntimeError("S3 presigned URL generation failed") from exc


s3_service = S3Service()
