# EN: Tests for DB schema description helper.
# KO: DB 스키마 설명 도우미 테스트입니다.

from app.db.describe_schema import describe_schema


def test_describe_schema_includes_core_tables() -> None:
    table_names = {table["table_name"] for table in describe_schema()}

    assert "documents" in table_names
    assert "document_chunks" in table_names
    assert "artifacts" in table_names
    assert "artifact_versions" in table_names
    assert "artifact_documents" in table_names
    assert "artifact_links" in table_names
    assert "templates" in table_names
    assert "projects" in table_names
    assert "action_items" in table_names
