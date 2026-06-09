# EN: CLI helper to verify configured DB and S3 runtime integrations.
# KO: 설정된 DB와 S3 런타임 연동을 확인하는 CLI 도우미입니다.

import asyncio
from uuid import uuid4

from sqlalchemy import text

from app.core.config import normalize_async_database_url, settings
from app.db.session import AsyncSessionLocal, dispose_db
from app.storage.s3 import S3Service


async def check_db() -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT 1"))
        value = result.scalar_one()
    print(f"DB OK | url={_mask_database_url(normalize_async_database_url(settings.DATABASE_URL))} | result={value}")


async def check_s3() -> None:
    if settings.S3_STORAGE_BACKEND.lower() != "s3":
        print(
            "S3 SKIPPED | "
            f"backend={settings.S3_STORAGE_BACKEND} | "
            "set S3_STORAGE_BACKEND=s3 in backend/.env for real AWS upload"
        )
        return

    service = S3Service()
    key = f"{settings.S3_UPLOAD_PREFIX}/integration-check/{uuid4().hex}.txt"
    storage_path = await service.upload(b"finpm integration check\n", key)
    print(
        "S3 OK | "
        f"backend={settings.S3_STORAGE_BACKEND} | "
        f"bucket={settings.S3_BUCKET_NAME} | "
        f"path={storage_path}"
    )


def _mask_database_url(url: str) -> str:
    if "@" not in url or "://" not in url:
        return url

    scheme, rest = url.split("://", 1)
    return f"{scheme}://***@{rest.split('@', 1)[1]}"


async def main() -> None:
    await check_db()
    await check_s3()
    await dispose_db()


if __name__ == "__main__":
    asyncio.run(main())
