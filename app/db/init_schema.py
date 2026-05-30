# EN: CLI helper to initialize SQLAlchemy tables for local or provisioned DBs.
# KO: 로컬 또는 생성된 DB에 SQLAlchemy 테이블을 초기화하는 CLI 도우미입니다.

import asyncio

from app.db.session import dispose_db, init_db


async def main() -> None:
    await init_db()
    await dispose_db()


if __name__ == "__main__":
    asyncio.run(main())
