# EN: CLI helper to print SQLAlchemy metadata tables before DB initialization.
# KO: DB 초기화 전 SQLAlchemy metadata 테이블 구성을 출력하는 CLI 도우미입니다.

from app.db.base import Base


def describe_schema() -> list[dict]:
    """Return a simple serializable description of registered DB tables."""
    tables: list[dict] = []
    for table in Base.metadata.sorted_tables:
        tables.append(
            {
                "table_name": table.name,
                "columns": [column.name for column in table.columns],
            }
        )

    return tables


def main() -> None:
    for table in describe_schema():
        print(table["table_name"])
        for column in table["columns"]:
            print(f"  - {column}")


if __name__ == "__main__":
    main()
