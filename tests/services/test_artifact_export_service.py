# EN: Tests for generated artifact file export behavior.
# KO: 생성 산출물 파일 export 동작 테스트입니다.

from io import BytesIO

from openpyxl import load_workbook
from pptx import Presentation

import app.db.base  # noqa: F401
from app.services.artifact_export_service import ArtifactExportService


def test_wbs_export_fills_hierarchical_display_ids(monkeypatch) -> None:
    monkeypatch.setattr(
        "util.agent_template_utils.settings.S3_STORAGE_BACKEND",
        "mock",
    )
    levels = [0, 1, 2, 3, 4, 4, 3, 4, 4, 3, 4, 4, 3, 4, 4]
    expected_ids = [
        "0",
        "1",
        "1.1",
        "1.1.1",
        "1.1.1.1",
        "1.1.1.2",
        "1.1.2",
        "1.1.2.1",
        "1.1.2.2",
        "1.1.3",
        "1.1.3.1",
        "1.1.3.2",
        "1.1.4",
        "1.1.4.1",
        "1.1.4.2",
    ]
    result_json = {
        "artifact_type": "WBS",
        "tasks": [
            {
                "task_id": f"WBS-{index:03d}",
                "name": f"Task {index}",
                "metadata": {"level": str(level)},
            }
            for index, level in enumerate(levels, start=1)
        ],
        "metadata": {"project_id": "PRJ-TEST-001", "author": "홍길동"},
    }

    file_bytes = ArtifactExportService()._build_wbs_xlsx(result_json)
    workbook = load_workbook(BytesIO(file_bytes), data_only=False)
    sheet = workbook["WBS"]

    actual_ids = [sheet.cell(row=row, column=3).value for row in range(2, 17)]

    assert actual_ids == expected_ids


def test_requirement_export_keeps_work_category_and_empty_review_note(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "util.agent_template_utils.settings.S3_STORAGE_BACKEND",
        "mock",
    )
    result_json = {
        "artifact_type": "REQUIREMENT_SPEC",
        "requirements": [
            {
                "requirement_id": "BSR-00001",
                "title": "시스템 아키텍쳐 설계",
                "description": "- 서비스별 독립성, 확장 유연성을 가질 수 있는 OCP 플랫폼 구축",
                "metadata": {
                    "work": "비대면 아키텍쳐 재설계 및 인프라 구축",
                    "section_category": "비대면 아키텍쳐 재설계 및 인프라 구축",
                    "biz_requirement_id": "Biz-0001",
                    "biz_requirement_name": "아키텍쳐 설계",
                    "category": "기능",
                    "creation_stage": "요구사항정의",
                    "status": "신규",
                    "source": "구축요건정의서",
                    "requirement_name": "시스템 아키텍쳐 설계",
                    "description": "- 서비스별 독립성, 확장 유연성을 가질 수 있는 OCP 플랫폼 구축",
                    "note": "",
                },
            }
        ],
        "metadata": {"project_id": "PRJ-TEST-001", "author": "홍길동"},
    }

    file_bytes = ArtifactExportService()._build_requirement_xlsx(result_json)
    workbook = load_workbook(BytesIO(file_bytes), data_only=True)
    sheet = workbook["요구사항명세서"]

    assert sheet.cell(row=2, column=1).value == "비대면 아키텍쳐 재설계 및 인프라 구축"
    assert sheet.cell(row=2, column=2).value == "비대면 아키텍쳐 재설계 및 인프라 구축"
    assert sheet.cell(row=2, column=5).value == "기능"
    assert sheet.cell(row=2, column=11).value == "- 서비스별 독립성, 확장 유연성을 가질 수 있는 OCP 플랫폼 구축"
    assert sheet.cell(row=2, column=16).value is None


def test_screen_design_export_creates_pages_with_requirement_descriptions(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "util.agent_template_utils.settings.S3_STORAGE_BACKEND",
        "mock",
    )
    result_json = {
        "artifact_type": "SCREEN_DESIGN",
        "screens": [
            {
                "screen_id": "SCR-001",
                "name": "회원 조회 화면",
                "description": "사용자는 회원 목록을 조회할 수 있어야 한다.",
                "source_requirement_ids": ["REQ-0001"],
                "metadata": {
                    "requirement_id": "REQ-0001",
                    "requirement_name": "회원 조회",
                    "description": "사용자는 회원 목록을 조회할 수 있어야 한다.",
                    "display_items": [
                        {
                            "item_name": "Description",
                            "description": "사용자는 회원 목록을 조회할 수 있어야 한다.",
                        }
                    ],
                },
            },
            {
                "screen_id": "SCR-002",
                "name": "권한 관리 화면",
                "description": "관리자는 사용자 권한을 변경할 수 있어야 한다.",
                "source_requirement_ids": ["REQ-0002"],
                "metadata": {
                    "requirement_id": "REQ-0002",
                    "requirement_name": "권한 관리",
                    "description": "관리자는 사용자 권한을 변경할 수 있어야 한다.",
                    "display_items": [
                        {
                            "item_name": "Description",
                            "description": "관리자는 사용자 권한을 변경할 수 있어야 한다.",
                        }
                    ],
                },
            },
        ],
        "metadata": {"project_id": "PRJ-TEST-001", "author": "홍길동"},
    }

    file_bytes = ArtifactExportService()._build_screen_design_pptx(result_json)
    presentation = Presentation(BytesIO(file_bytes))
    texts = []
    for slide in presentation.slides:
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False):
                texts.append(shape.text)
            if getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    for cell in row.cells:
                        texts.append(cell.text)
    all_text = "\n".join(texts)

    assert "홍길동" in all_text
    assert "REQ-0001" in all_text
    assert "REQ-0002" in all_text
    assert "사용자는 회원 목록을 조회할 수 있어야 한다." in all_text
    assert "작업 내용을 정의한다" not in all_text
    assert "검색 조건" not in all_text
    assert "처리 버튼" not in all_text
    description_cell, style_cell = _first_description_value_and_style_cells(
        presentation,
    )
    assert description_cell.text == "사용자는 회원 목록을 조회할 수 있어야 한다."
    assert "REQ-0001" not in description_cell.text
    assert "회원 조회" not in description_cell.text
    assert "Description:" not in description_cell.text
    description_run = _first_run(description_cell)
    style_run = _first_run(style_cell)
    assert description_run is not None
    assert style_run is not None
    assert description_run.font.size == style_run.font.size
    assert description_run.font.bold == style_run.font.bold


def _first_description_value_and_style_cells(presentation):
    for slide in presentation.slides:
        for shape in slide.shapes:
            if not getattr(shape, "has_table", False):
                continue
            table = shape.table
            if len(table.rows) < 2 or len(table.columns) < 2:
                continue
            if table.cell(0, 0).text.replace("\n", "").strip() != "Description":
                continue
            return table.cell(1, 1), table.cell(1, 0)
    raise AssertionError("Description table not found")


def _first_run(cell):
    for paragraph in cell.text_frame.paragraphs:
        runs = list(paragraph.runs)
        if runs:
            return runs[0]
    return None
