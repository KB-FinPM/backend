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
                            "회원 | - 회원\\n조회 | - 회원 목록을 조회한다.\\n- 회원 상세 정보를 제공한다.",
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


def test_extracts_three_column_description_top_bullets_as_requirement_names() -> None:
    atoms = assign_requirement_ids(
        extract_requirement_atoms_from_pipe_tables(
            [
                {
                    "chunk_id": "CHUNK-001",
                    "document_id": "DOC-001",
                    "section_title": "상세요건",
                    "text": "\n".join(
                        [
                            "업무 | 구분 | 기능/비기능요구사항",
                            (
                                "환율 관리 | 고시 관리 | "
                                "o 실시간 환율 채집 및 고시 관리 기능\\n"
                                "- 시장 LP 및 CMBS로부터의 시장 환율을 채집 및 고시\\n"
                                "- 시장 채집 불가한 환율 및 Swap PT의 경우 수기 입력 기능 구현\\n"
                                "ㅇ Pricing 기능\\n"
                                "- 시장에서 채집하는 환율에 일정한 Spread 및 Skew를 설정 및 조회할 수 있는 기능 구현\\n"
                                "- Pricing 그룹 설정 및 관리 기능\\n"
                                "o 채집 및 고시된 환율을 직원이 기간별로 조회할 수 있는 화면 구현"
                            ),
                        ]
                    ),
                }
            ]
        )
    )

    assert [atom.biz_requirement_name for atom in atoms] == ["환율 관리", "환율 관리", "환율 관리"]
    assert [atom.requirement_name for atom in atoms] == [
        "실시간 환율 채집 및 고시 관리 기능",
        "Pricing 기능",
        "채집 및 고시된 환율을 직원이 기간별로 조회할 수 있는 화면 구현",
    ]
    assert atoms[0].description == (
        "- 시장 LP 및 CMBS로부터의 시장 환율을 채집 및 고시\n"
        "- 시장 채집 불가한 환율 및 Swap PT의 경우 수기 입력 기능 구현"
    )
    assert atoms[1].description == (
        "- 시장에서 채집하는 환율에 일정한 Spread 및 Skew를 설정 및 조회할 수 있는 기능 구현\n"
        "- Pricing 그룹 설정 및 관리 기능"
    )
    assert atoms[2].description == " "


def test_extracts_explicit_three_column_description_top_bullets_as_requirement_names() -> None:
    atoms = assign_requirement_ids(
        extract_requirement_atoms_from_pipe_tables(
            [
                {
                    "chunk_id": "CHUNK-001",
                    "document_id": "DOC-001",
                    "section_title": "상세요건",
                    "text": "\n".join(
                        [
                            "Biz요건명 | 요구사항명 | 기능/비기능요구사항",
                            (
                                "환율 관리 | 고시 관리 | "
                                "o 실시간 환율 채집 및 고시 관리 기능\\n"
                                "- 시장 LP 및 CMBS로부터의 시장 환율을 채집 및 고시\\n"
                                "- 시장 채집 불가한 환율 및 Swap PT의 경우 수기 입력 기능 구현\\n"
                                "ㅇ Pricing 기능\\n"
                                "- 시장에서 채집하는 환율에 일정한 Spread 및 Skew를 설정 및 조회할 수 있는 기능 구현\\n"
                                "- Pricing 그룹 설정 및 관리 기능\\n"
                                "o 채집 및 고시된 환율을 직원이 기간별로 조회할 수 있는 화면 구현"
                            ),
                        ]
                    ),
                }
            ]
        )
    )

    assert [atom.biz_requirement_name for atom in atoms] == ["환율 관리", "환율 관리", "환율 관리"]
    assert [atom.requirement_name for atom in atoms] == [
        "실시간 환율 채집 및 고시 관리 기능",
        "Pricing 기능",
        "채집 및 고시된 환율을 직원이 기간별로 조회할 수 있는 화면 구현",
    ]
    assert atoms[0].description == (
        "- 시장 LP 및 CMBS로부터의 시장 환율을 채집 및 고시\n"
        "- 시장 채집 불가한 환율 및 Swap PT의 경우 수기 입력 기능 구현"
    )
    assert atoms[1].description == (
        "- 시장에서 채집하는 환율에 일정한 Spread 및 Skew를 설정 및 조회할 수 있는 기능 구현\n"
        "- Pricing 그룹 설정 및 관리 기능"
    )
    assert atoms[2].description == " "


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
                            "검색 기능 | ㅇ 검색 조건\\n- 사용자는 조건을 입력해 목록을 조회할 수 있어야 한다.",
                            "검색 기능 | * 엑셀 다운로드 - 조회 결과를 엑셀로 다운로드할 수 있어야 한다.",
                            "검색 기능 | o 고급 검색 o 기간 조건을 제공한다. O 상태 조건을 제공한다.",
                            "환율 관리 | - 시장 환율을 채집 및 고시\\n- 수기 입력 기능 구현\\n  o Pricing 기능\\n- Spread 및 Skew 설정 기능 구현\\n  - Pricing 그룹 설정 및 관리 기능",
                            "환율 관리 | - 직원 기간별 조회 및 통계 - 직원 매체별 조회 및 통계   - 직원 화면 권한 조회",
                        ]
                    ),
                }
            ]
        )
    )

    assert [atom.biz_requirement_name for atom in atoms] == [
        "검색 기능",
        "검색 기능",
        "검색 기능",
        "검색 기능",
        "검색 기능",
        "검색 기능",
        "환율 관리",
        "환율 관리",
        "환율 관리",
        "환율 관리",
        "환율 관리",
        "환율 관리",
        "환율 관리",
        "환율 관리",
    ]
    assert [atom.requirement_name for atom in atoms] == [
        "검색 조건",
        "엑셀 다운로드",
        "조회 결과를 엑셀로 다운로드할 수 있어야 한다.",
        "고급 검색",
        "기간 조건을 제공한다.",
        "상태 조건을 제공한다.",
        "시장 환율을 채집 및 고시",
        "수기 입력 기능 구현",
        "Pricing 기능",
        "Spread 및 Skew 설정 기능 구현",
        "Pricing 그룹 설정 및 관리 기능",
        "직원 기간별 조회 및 통계",
        "직원 매체별 조회 및 통계",
        "직원 화면 권한 조회",
    ]
    assert atoms[0].biz_requirement_id == atoms[1].biz_requirement_id == atoms[2].biz_requirement_id == "Biz-0001"
    assert atoms[6].biz_requirement_id == atoms[7].biz_requirement_id == atoms[8].biz_requirement_id == "Biz-0002"
    assert atoms[0].category == "기능"
    assert atoms[0].domain == "요건내용"
    assert atoms[0].description == "- 사용자는 조건을 입력해 목록을 조회할 수 있어야 한다."
    assert atoms[2].description == "조회 결과를 엑셀로 다운로드할 수 있어야 한다."
    assert atoms[3].description == " "
    assert atoms[8].description == "Pricing 기능"
    assert atoms[10].description == "Pricing 그룹 설정 및 관리 기능"
    assert atoms[13].description == "직원 화면 권한 조회"


def test_extracts_uploaded_two_column_circle_bullets_as_parent_requirements() -> None:
    atoms = assign_requirement_ids(
        extract_requirement_atoms_from_pipe_tables(
            [
                {
                    "chunk_id": "CHUNK-001",
                    "document_id": "DOC-001",
                    "section_title": "ROOT / part-1",
                    "text": "\n".join(
                        [
                            "구 분 | 주요내용",
                            "시장 거래 | o 시장거래\\n- 현물환 시장 거래 제공\\n- 다양한 주문유형 제공: 솔루션 제공 주문유형",
                            "환율 고시\\n및 조회 | o 실시간 환율 채집 및 고시 관리 기능\\n- 시장 LP 및 CMBS로부터의 시장 환율을 채집 및 고시\\n- 시장 채집 불가한 환율 및 Swap PT의 경우 수기 입력 기능 구현\\nㅇ Pricing 기능\\n- 시장에서 채집하는 환율에 일정한 Spread 및 Skew를 설정 및 조회할 수 있는 기능 구현\\n- Pricing 그룹 설정 및 관리 기능\\no 채집 및 고시된 환율을 직원이 기간별로 조회할 수 있는 화면 구현",
                        ]
                    ),
                }
            ]
        )
    )

    assert [atom.biz_requirement_name for atom in atoms] == [
        "시장 거래",
        "환율 고시 및 조회",
        "환율 고시 및 조회",
        "환율 고시 및 조회",
    ]
    assert [atom.requirement_name for atom in atoms] == [
        "시장거래",
        "실시간 환율 채집 및 고시 관리 기능",
        "Pricing 기능",
        "채집 및 고시된 환율을 직원이 기간별로 조회할 수 있는 화면 구현",
    ]
    assert atoms[0].description == (
        "- 현물환 시장 거래 제공\n"
        "- 다양한 주문유형 제공: 솔루션 제공 주문유형"
    )
    assert atoms[1].description == (
        "- 시장 LP 및 CMBS로부터의 시장 환율을 채집 및 고시\n"
        "- 시장 채집 불가한 환율 및 Swap PT의 경우 수기 입력 기능 구현"
    )
    assert atoms[2].description == (
        "- 시장에서 채집하는 환율에 일정한 Spread 및 Skew를 설정 및 조회할 수 있는 기능 구현\n"
        "- Pricing 그룹 설정 및 관리 기능"
    )
    assert atoms[3].description == " "


def test_keeps_final_top_bullet_without_child_description() -> None:
    atoms = assign_requirement_ids(
        extract_requirement_atoms_from_pipe_tables(
            [
                {
                    "chunk_id": "CHUNK-001",
                    "document_id": "DOC-001",
                    "section_title": "상세요건",
                    "text": "\n".join(
                        [
                            "구 분 | 주요내용",
                            (
                                "내부 거래 | "
                                "ㅇ 내부 거래: 직원간 거래 기능\\n"
                                "- 현물환, 선물환, 외환스왑, MAR거래 제공\\n"
                                "- RFQ 주문 기능 제공 (쿼트 요청이 발생 시 딜러에게 팝업 알림 기능 필요)\\n"
                                "- 거래 상대방/북 지정 기능\\n"
                                "- 가상 잔량 반영된 체결 기능\\n"
                                "ㅇ 대량거래 입력 기능(세일즈 거래에 한함)"
                            ),
                        ]
                    ),
                }
            ]
        )
    )

    assert [atom.requirement_name for atom in atoms] == [
        "내부 거래: 직원간 거래 기능",
        "대량거래 입력 기능(세일즈 거래에 한함)",
    ]
    assert atoms[0].description == (
        "- 현물환, 선물환, 외환스왑, MAR거래 제공\n"
        "- RFQ 주문 기능 제공 (쿼트 요청이 발생 시 딜러에게 팝업 알림 기능 필요)\n"
        "- 거래 상대방/북 지정 기능\n"
        "- 가상 잔량 반영된 체결 기능"
    )
    assert atoms[1].description == " "


def test_extracts_requirement_name_description_header_table() -> None:
    atoms = assign_requirement_ids(
        extract_requirement_atoms_from_pipe_tables(
            [
                {
                    "chunk_id": "CHUNK-001",
                    "document_id": "DOC-001",
                    "section_title": "요건내용",
                    "text": "\n".join(
                        [
                            "요구사항명 | 기능/비기능요구사항",
                            "실시간 환율 채집 및 고시 관리 기능 | - 시장 LP 및 CMBS로부터의 시장 환율을 채집 및 고시\\n- 시장 채집 불가한 환율 및 Swap PT의 경우 수기 입력 기능 구현\\nㅇ Pricing 기능\\n- 시장에서 채집하는 환율에 일정한 Spread 및 Skew를 설정 및 조회할 수 있는 기능 구현\\n- Pricing 그룹 설정 및 관리 기능\\nㅇ 채집 및 고시된 환율을 직원이 기간별로 조회할 수 있는 화면 구현",
                        ]
                    ),
                }
            ]
        )
    )

    assert [atom.requirement_name for atom in atoms] == [
        "실시간 환율 채집 및 고시 관리 기능",
        "Pricing 기능",
        "채집 및 고시된 환율을 직원이 기간별로 조회할 수 있는 화면 구현",
    ]
    assert atoms[0].description == (
        "- 시장 LP 및 CMBS로부터의 시장 환율을 채집 및 고시\n"
        "- 시장 채집 불가한 환율 및 Swap PT의 경우 수기 입력 기능 구현"
    )
    assert atoms[1].description == (
        "- 시장에서 채집하는 환율에 일정한 Spread 및 Skew를 설정 및 조회할 수 있는 기능 구현\n"
        "- Pricing 그룹 설정 및 관리 기능"
    )
    assert atoms[2].description == " "


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
