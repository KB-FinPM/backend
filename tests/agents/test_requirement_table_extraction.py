# EN: Tests for construction-definition table extraction rules.
# KO: 구축요건정의서 표 추출 규칙 테스트입니다.

from util.agent_generation_utils import (
    assign_requirement_ids,
    extract_requirement_atoms_from_pipe_tables,
)


def test_extracts_three_column_requirement_table_with_section_title() -> None:
    atoms = assign_requirement_ids(
        extract_requirement_atoms_from_pipe_tables(
            [
                {
                    "chunk_id": "CHUNK-001",
                    "document_id": "DOC-001",
                    "section_title": "상세요건",
                    "text": "\n".join(
                        [
                            "개요",
                            "시스템 개요 | 설명 | 구축 대상 범위를 소개한다",
                            "개발상세",
                            "회원 | 회원\\n조회 | - 회원 목록을 조회한다.\\n- 회원 상세 정보를 제공한다.",
                            "회원 | 회원 등록 | 회원 정보를 등록하고 검증 메시지를 제공한다.",
                            "권한 | 권한 관리 | 관리자 권한을 부여하고 변경 이력을 관리한다.",
                            "주 1) 본 표의 용어는 추후 변경될 수 있음",
                        ]
                    ),
                }
            ]
        )
    )

    assert [atom.biz_requirement_name for atom in atoms] == ["회원", "회원", "권한"]
    assert [atom.biz_requirement_id for atom in atoms] == [
        "Biz-0001",
        "Biz-0001",
        "Biz-0002",
    ]
    assert atoms[0].requirement_id == "BSR-00001"
    assert atoms[0].requirement_name == "회원 조회"
    assert atoms[0].description == "- 회원 목록을 조회한다.\n- 회원 상세 정보를 제공한다."
    assert atoms[0].category == "기능"
    assert atoms[0].domain == "개발상세"


def test_extracts_two_column_requirement_table() -> None:
    atoms = assign_requirement_ids(
        extract_requirement_atoms_from_pipe_tables(
            [
                {
                    "chunk_id": "CHUNK-001",
                    "document_id": "DOC-001",
                    "section_title": "수립방안",
                    "text": "\n".join(
                        [
                            "요건내용",
                            "검색 기능 | 사용자는 조건을 입력해 목록을 조회할 수 있어야 한다.",
                            "검색 기능 | 조회 결과를 엑셀로 다운로드할 수 있어야 한다.",
                        ]
                    ),
                }
            ]
        )
    )

    assert [atom.biz_requirement_name for atom in atoms] == ["검색 기능", "검색 기능"]
    assert [atom.requirement_name for atom in atoms] == ["검색 기능", "검색 기능"]
    assert atoms[0].biz_requirement_id == atoms[1].biz_requirement_id == "Biz-0001"
    assert atoms[0].category == "기능"
    assert atoms[0].domain == "요건내용"
    assert "목록을 조회" in atoms[0].description


def test_skips_excluded_sections_and_note_lines() -> None:
    atoms = extract_requirement_atoms_from_pipe_tables(
        [
            {
                "chunk_id": "CHUNK-001",
                "document_id": "DOC-001",
                "section_title": "개요",
                "text": "\n".join(
                    [
                        "개요",
                        "회원 | 회원 조회 | 회원 목록을 조회하고 상세 정보를 제공한다.",
                        "별첨",
                        "권한 | 권한 관리 | 권한 변경 기능을 제공한다.",
                        "상세요건",
                        "주 1) 아래 내용은 예시임",
                        "알림 | 알림 관리 | 알림 발송 이력을 조회하고 관리한다.",
                    ]
                ),
            }
        ]
    )

    assert len(atoms) == 1
    assert atoms[0].biz_requirement_name == "알림"
