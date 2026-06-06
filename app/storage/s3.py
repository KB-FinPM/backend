# EN: S3 storage service wrapper for document and artifact files.
# KO: 문서와 산출물 파일을 다루는 S3 저장소 서비스 래퍼입니다.

import asyncio

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)


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
                verify=self._ssl_verify_setting(),
            )

    def _ssl_verify_setting(self) -> bool | str:
        if settings.AWS_CA_BUNDLE:
            return settings.AWS_CA_BUNDLE

        return settings.AWS_VERIFY_SSL

    async def upload(self, file_bytes: bytes, key: str, content_type: str | None = None) -> str:
        logger.info(f"[S3] upload | backend={self.backend} | bucket={self.bucket} | key={key}")
        if self.client is None:
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
