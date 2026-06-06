# EN: Exports generated artifact JSON to user-facing files and uploads them.
# KO: 생성 산출물 JSON을 사용자 파일로 변환하고 S3에 업로드합니다.

from __future__ import annotations

import json
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath
from typing import Any
from uuid import uuid4

from app.core.config import settings
from app.core.logger import get_logger
from app.schemas.artifact import ArtifactType, DocumentMetadata, DocumentType
from app.services.document_service import DocumentService
from app.storage.s3 import S3Service, s3_service
from util.agent_template_utils import (
    build_placeholder_values,
    build_template_context,
    get_nested,
    get_value,
    load_output_mapper,
    output_file_name,
    resolve_template_path,
)

logger = get_logger(__name__)


@dataclass(frozen=True)
class ArtifactExportResult:
    storage_path: str
    file_name: str
    content_type: str
    document: DocumentMetadata | None = None


class ArtifactExportService:
    """Creates xlsx/pptx files for generated artifacts.

    Requirement specs are also registered as generated REQUIREMENT_SPEC documents
    so WBS and screen-design generation can use the returned document_id as their
    source document.
    """

    async def export_artifact(
        self,
        *,
        project_id: str,
        artifact_id: str,
        artifact_type: ArtifactType,
        result_json: dict[str, Any],
        document_service: DocumentService | None = None,
        storage_service: S3Service | None = None,
    ) -> ArtifactExportResult | None:
        if artifact_type == ArtifactType.REQUIREMENT_SPEC:
            file_name = output_file_name("requirement_spec", "요구사항명세서.xlsx")
            file_bytes = self._build_requirement_xlsx(result_json)
            content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        elif artifact_type == ArtifactType.WBS:
            file_name = output_file_name("wbs", "WBS.xlsx")
            file_bytes = self._build_wbs_xlsx(result_json)
            content_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        elif artifact_type == ArtifactType.SCREEN_DESIGN:
            file_name = output_file_name("screen_plan", "화면기획서.pptx")
            file_bytes = self._build_screen_design_pptx(result_json)
            content_type = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        else:
            return None

        safe_file_name = PurePath(file_name).name
        storage_key = (
            f"{settings.S3_GENERATED_PREFIX}/{project_id}/"
            f"{artifact_type.value}/{artifact_id}/{safe_file_name}"
        )
        # Use the same storage service that handled the upload API whenever it is
        # available. This prevents generated artifacts from accidentally using a
        # different/global S3 backend configuration than uploaded source files.
        active_storage_service = (
            storage_service
            or (document_service.storage_service if document_service is not None else None)
            or s3_service
        )
        storage_path = await active_storage_service.upload(
            file_bytes=file_bytes,
            key=storage_key,
            content_type=content_type,
        )
        logger.info(
            "[ArtifactExport] exported | "
            f"project_id={project_id} | artifact_id={artifact_id} | "
            f"file_name={safe_file_name} | path={storage_path}"
        )

        generated_document = None
        if artifact_type == ArtifactType.REQUIREMENT_SPEC and document_service is not None:
            document_id = f"DOC-{uuid4().hex[:12].upper()}"
            generated_document = await document_service.ingest_uploaded_document(
                document_id=document_id,
                project_id=project_id,
                document_type=DocumentType.REQUIREMENT_SPEC,
                file_name=safe_file_name,
                storage_path=storage_path,
                file_bytes=file_bytes,
                parsed_context={
                    "text": self._requirement_text(result_json),
                    "requirements": result_json.get("requirements", []),
                    "metadata": {
                        "generated_from_artifact_id": artifact_id,
                        "artifact_type": artifact_type.value,
                        "source_file_name": safe_file_name,
                        "content_type": content_type,
                    },
                    "parser_name": "ArtifactExportService",
                },
            )

        return ArtifactExportResult(
            storage_path=storage_path,
            file_name=safe_file_name,
            content_type=content_type,
            document=generated_document,
        )

    def _requirement_text(self, result_json: dict[str, Any]) -> str:
        lines = ["# REQUIREMENT_SPEC"]
        for item in result_json.get("requirements", []):
            metadata = item.get("metadata") or {}
            lines.append(
                " | ".join(
                    [
                        str(item.get("requirement_id", "")),
                        str(metadata.get("biz_requirement_name", "")),
                        str(metadata.get("domain", "")),
                        str(item.get("title", "")),
                        str(item.get("description", "")),
                    ]
                )
            )
        return "\n".join(lines)

    def _build_requirement_xlsx(self, result_json: dict[str, Any]) -> bytes:
        from openpyxl import Workbook, load_workbook
        from openpyxl.cell.cell import MergedCell

        mapper = load_output_mapper()
        req_mapper = get_nested(mapper, "requirement_spec", default={}) or {}
        sheet_cfg = req_mapper.get("data_sheet") or {}
        columns = self._legacy_requirement_columns(sheet_cfg.get("columns") or [])
        context = build_template_context(project_id=str((result_json.get("metadata") or {}).get("project_id") or ""), context=result_json.get("metadata") or {})

        template_path = req_mapper.get("template_path")
        if template_path:
            wb = load_workbook(resolve_template_path(template_path))
            self._apply_placeholder_sheets(wb, req_mapper.get("placeholder_sheets", []), context)
            target_sheet_name = sheet_cfg.get("sheet_name", "요구사항명세서")
            target_sheet_names = [target_sheet_name]
            # Existing requirement templates used by the team expose the same
            # requirement table through legacy sheets such as 감리제출용. Fill
            # them as well when present so the output matches pre-merge files.
            for legacy_name in ["감리제출용", "(요건분리 전)요구사항명세서"]:
                if legacy_name in wb.sheetnames and legacy_name not in target_sheet_names:
                    target_sheet_names.append(legacy_name)
            for sheet_name in target_sheet_names:
                if sheet_name not in wb.sheetnames:
                    continue
                ws = wb[sheet_name]
                self._write_mapped_rows(ws, result_json.get("requirements", []), sheet_cfg, columns, context, self._requirement_source)
            return self._save_workbook(wb)

        wb = Workbook()
        ws = wb.active
        ws.title = sheet_cfg.get("sheet_name") or "요구사항명세서"
        headers = [(column.get("header_names") or [column.get("field", "")])[0] for column in columns] or ["구분", "Biz요건ID", "Biz요건명", "요구사항ID", "요구사항명", "기능/비기능요구사항", "검토의견"]
        ws.append(headers)
        for row_number, item in enumerate(result_json.get("requirements", []), start=1):
            source = self._requirement_source(item)
            ws.append([get_value(source, column.get("field"), context=context, row_number=row_number) for column in columns] if columns else [
                source.get("category", ""), source.get("biz_requirement_id", ""), source.get("biz_requirement_name") or source.get("domain", ""), source.get("requirement_id", ""), source.get("requirement_name", ""), source.get("requirement_type", ""), source.get("note") or source.get("description", ""),
            ])
        self._style_sheet(ws, widths=[18, 18, 24, 18, 36, 22, 60, 20, 20, 20, 20, 20, 20, 20, 20, 60])
        return self._save_workbook(wb)

    def _build_wbs_xlsx(self, result_json: dict[str, Any]) -> bytes:
        from openpyxl import Workbook, load_workbook

        mapper = load_output_mapper()
        wbs_mapper = get_nested(mapper, "wbs", default={}) or {}
        sheet_cfg = wbs_mapper.get("data_sheet") or {}
        columns = sheet_cfg.get("columns") or []
        context = build_template_context(project_id=str((result_json.get("metadata") or {}).get("project_id") or ""), context=result_json.get("metadata") or {})
        tasks = self._normalize_wbs_hierarchy(result_json.get("tasks", []), project_name=context.get("project_name") or context.get("project_id") or "프로젝트명")

        template_path = wbs_mapper.get("template_path")
        if template_path:
            wb = load_workbook(resolve_template_path(template_path))
            ws = wb[sheet_cfg.get("sheet_name", "WBS")]
            self._write_mapped_rows(ws, tasks, sheet_cfg, columns, context, self._wbs_source)
            return self._save_workbook(wb)

        wb = Workbook()
        ws = wb.active
        ws.title = sheet_cfg.get("sheet_name") or "WBS"
        headers = [(column.get("header_names") or [column.get("field", "")])[0] for column in columns] or ["NO", "레벨", "ID", "WBS명", "산출물"]
        ws.append(headers)
        for row_number, task in enumerate(tasks, start=1):
            source = self._wbs_source(task)
            ws.append([get_value(source, column.get("field"), context=context, row_number=row_number) for column in columns] if columns else [row_number, source.get("level", ""), source.get("id", ""), source.get("wbs_name", ""), source.get("deliverable", "")])
        self._style_sheet(ws, widths=[10, 10, 18, 48, 34, 20, 20, 34, 20])
        return self._save_workbook(wb)

    def _build_screen_design_pptx(self, result_json: dict[str, Any]) -> bytes:
        from copy import deepcopy
        from pptx import Presentation
        from pptx.util import Inches, Pt

        mapper = load_output_mapper()
        screen_mapper = get_nested(mapper, "screen_plan", default={}) or {}
        context = build_template_context(project_id=str((result_json.get("metadata") or {}).get("project_id") or ""), context=result_json.get("metadata") or {})
        template_path = screen_mapper.get("template_path")

        if template_path:
            prs = Presentation(resolve_template_path(template_path))
            common_values = self._common_screen_placeholder_values(screen_mapper, context)
            self._replace_placeholders_in_presentation(prs, common_values)
            template_slide_index = int(screen_mapper.get("template_slide_index", 2))
            screen_placeholders = get_nested(screen_mapper, "placeholder_slides", "screen_item", default={}) or {}
            table_mapper = screen_mapper.get("description_table") or {}
            for screen in result_json.get("screens", []):
                slide = self._duplicate_slide(prs, template_slide_index)
                source = self._screen_source(screen)
                values = {}
                values.update(common_values)
                values.update(build_placeholder_values(screen_placeholders, source=source, context=context))
                values.update(self._screen_placeholder_values(source, context))
                self._replace_placeholders_in_slide(slide, values)
                filled = self._fill_description_table(slide, source, table_mapper)
                if not filled:
                    self._add_description_fallback(slide, source)
                self._replace_placeholders_in_slide(slide, values)
            if template_slide_index < len(prs.slides):
                self._delete_slide(prs, template_slide_index)
            self._replace_placeholders_in_presentation(prs, common_values)
            bio = BytesIO()
            prs.save(bio)
            return bio.getvalue()

        prs = Presentation()
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)

        title_slide = prs.slides.add_slide(prs.slide_layouts[0])
        title_slide.shapes.title.text = "화면설계서"
        title_slide.placeholders[1].text = "Generated by PM Artifact Agent"

        for screen in result_json.get("screens", []):
            source = self._screen_source(screen)
            slide = prs.slides.add_slide(self._get_blank_slide_layout(prs))
            title = slide.shapes.add_textbox(Inches(0.4), Inches(0.25), Inches(12.4), Inches(0.55))
            title_tf = title.text_frame
            title_tf.text = f"{source.get('screen_id', '')}  {source.get('screen_name', '')}"
            title_tf.paragraphs[0].font.size = Pt(20)
            title_tf.paragraphs[0].font.bold = True

            placeholder = slide.shapes.add_shape(1, Inches(0.5), Inches(1.05), Inches(7.5), Inches(5.95))
            placeholder.text = "화면 기획 내용 이미지 영역"
            placeholder.text_frame.paragraphs[0].font.size = Pt(18)

            rows = max(2, min(8, len(source.get("display_items", [])) + 1))
            table_shape = slide.shapes.add_table(rows, 2, Inches(8.25), Inches(1.05), Inches(4.65), Inches(5.95))
            table = table_shape.table
            table.cell(0, 0).text = "표시항목"
            table.cell(0, 1).text = "설명"
            for idx, item in enumerate(source.get("display_items", [])[: rows - 1], start=1):
                table.cell(idx, 0).text = str(item.get("item_name", ""))
                table.cell(idx, 1).text = str(item.get("description", ""))

            note = slide.shapes.add_textbox(Inches(0.5), Inches(6.95), Inches(12.3), Inches(0.35))
            note.text_frame.text = f"연관 요구사항: {source.get('requirement_id', '')}"
            note.text_frame.paragraphs[0].font.size = Pt(10)

        bio = BytesIO()
        prs.save(bio)
        return bio.getvalue()


    def _legacy_requirement_columns(self, columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
        legacy_columns = [
            {"field": "biz_requirement_id", "header_names": ["Biz요건ID", "Biz 요건 ID"], "default_column": 1},
            {"field": "biz_requirement_name|domain", "header_names": ["Biz요건명", "업무", "업무명"], "default_column": 2},
            {"field": "category", "header_names": ["요구사항구분", "구분"], "default_column": 3},
            {"field": "creation_stage", "header_names": ["생성단계"], "optional": True, "default_column": 4},
            {"field": "status", "header_names": ["상태구분", "상태"], "optional": True, "default_column": 5},
            {"field": "source", "header_names": ["출처"], "optional": True, "default_column": 6},
            {"field": "requirement_id", "header_names": ["요구사항ID"], "default_column": 7},
            {"field": "requirement_name", "header_names": ["요구사항명"], "default_column": 8},
            {"field": "description", "header_names": ["기능/비기능요구사항", "기능/비기능요구사항(취합정리 5/25)", "요구사항내용"], "default_column": 9},
            {"field": "user_auth_requirement", "header_names": ["사용자권한요구사항"], "optional": True, "default_column": 10},
            {"field": "request_dept", "header_names": ["의뢰부서"], "optional": True, "default_column": 11},
            {"field": "owner_team", "header_names": ["요구사항처리담당팀"], "optional": True, "default_column": 12},
            {"field": "review_status", "header_names": ["검토 상태", "검토상태"], "optional": True, "default_column": 13},
            {"field": "note", "header_names": ["검토의견"], "optional": True, "default_column": 14},
            {"field": "change_requirement_id", "header_names": ["변경요구사항ID"], "optional": True, "default_column": 15},
            {"field": "change_date", "header_names": ["변경일"], "optional": True, "default_column": 16},
            {"field": "source_doc", "header_names": ["근기문서", "근거문서"], "optional": True, "default_column": 17},
            {"field": "ace", "header_names": ["ACE"], "optional": True, "default_column": 18},
        ]
        merged = list(columns or [])
        seen_fields = {str(column.get("field")) for column in merged if isinstance(column, dict)}
        for column in legacy_columns:
            if column["field"] not in seen_fields:
                merged.append(column)
        return merged

    def _requirement_source(self, item: dict[str, Any]) -> dict[str, Any]:
        metadata = item.get("metadata") or {}
        return {
            **metadata,
            **item,
            "requirement_id": item.get("requirement_id") or metadata.get("requirement_id", ""),
            "requirement_name": metadata.get("requirement_name") or item.get("title", ""),
            "description": metadata.get("description") or item.get("description", ""),
            "note": metadata.get("note") or item.get("description", ""),
        }

    def _normalize_wbs_hierarchy(self, tasks: list[dict[str, Any]], project_name: str = "프로젝트명") -> list[dict[str, Any]]:
        """Ensure WBS rows always have display IDs like 0, 1, 1.1, 1.1.1.

        The agent normally assigns ``wbs_id`` already, but export can receive
        older artifacts or template rows that only have ``level``.  Recompute the
        display ID immediately before Excel writing so the S3 file always uses
        the expected hierarchy format.
        """
        normalized: list[dict[str, Any]] = []
        counters: list[int] = []
        for raw in tasks or []:
            task = dict(raw or {})
            metadata = dict(task.get("metadata") or {})
            try:
                level = int(str(metadata.get("level", task.get("level", "0"))).strip() or "0")
            except ValueError:
                level = 0
            level = max(level, 0)
            if level == 0:
                counters = [0]
                wbs_id = "0"
                if not str(task.get("name") or "").strip() or str(task.get("name")).strip() in {"프로젝트", "프로젝트명"}:
                    task["name"] = project_name or "프로젝트명"
            else:
                while len(counters) <= level:
                    counters.append(0)
                counters = counters[: level + 1]
                counters[level] += 1
                for idx in range(1, level):
                    if counters[idx] == 0:
                        counters[idx] = 1
                wbs_id = ".".join(str(counters[idx]) for idx in range(1, level + 1))
            metadata["level"] = str(level)
            metadata["wbs_id"] = wbs_id
            task["level"] = str(level)
            task["wbs_id"] = wbs_id
            normalized.append(task)
        return normalized

    def _wbs_source(self, task: dict[str, Any]) -> dict[str, Any]:
        metadata = task.get("metadata") or {}
        return {
            **metadata,
            **task,
            "id": task.get("wbs_id") or metadata.get("wbs_id") or task.get("task_id", ""),
            "wbs_name": task.get("name", ""),
            "deliverable": metadata.get("deliverable", ""),
        }

    def _screen_source(self, screen: dict[str, Any]) -> dict[str, Any]:
        metadata = screen.get("metadata") or {}
        source_requirement_ids = screen.get("source_requirement_ids") or []
        return {
            **metadata,
            **screen,
            "screen_name": screen.get("name", ""),
            "screen_no": screen.get("screen_id", ""),
            "requirement_id": metadata.get("requirement_id") or ", ".join(source_requirement_ids),
            "requirement_name": metadata.get("requirement_name") or screen.get("name", ""),
            "description": metadata.get("description") or screen.get("description", ""),
            "display_items": metadata.get("display_items", []),
        }

    def _common_screen_placeholder_values(self, mapper: dict[str, Any], context: dict[str, str]) -> dict[str, str]:
        values = build_placeholder_values(get_nested(mapper, "placeholder_slides", "common", default={}) or {}, context=context)
        project_name = context.get("project_name") or context.get("project_id") or "프로젝트명"
        values.update({
            "{프로젝트명}": project_name,
            "{ProjectName}": project_name,
            "{PROJECT_NAME}": project_name,
            "{작성일}": context.get("today", ""),
            "{작성자}": context.get("author", ""),
            "{작성자명}": context.get("author", ""),
        })
        return values

    def _screen_placeholder_values(self, source: dict[str, Any], context: dict[str, str]) -> dict[str, str]:
        requirement_id = str(source.get("requirement_id") or "")
        screen_id = str(source.get("screen_id") or source.get("screen_no") or "")
        screen_name = str(source.get("screen_name") or source.get("name") or "")
        requirement_name = str(source.get("requirement_name") or screen_name)
        description = str(source.get("description") or "")
        return {
            "{프로젝트명}": context.get("project_name") or context.get("project_id") or "프로젝트명",
            "{작성일}": context.get("today", ""),
            "{작성자}": context.get("author", ""),
            "{작성자명}": context.get("author", ""),
            "{요구사항ID}": requirement_id,
            "{요구사항명}": requirement_name,
            "{요구사항내용}": description,
            "{Description}": description,
            "{DESCRIPTION}": description,
            "{description}": description,
            "{화면ID}": screen_id,
            "{화면번호}": screen_id,
            "{화면명}": screen_name,
            "{서브시스템명}": str(source.get("biz_requirement_name") or source.get("domain") or ""),
            "{메뉴위치}": str(source.get("domain") or source.get("biz_requirement_name") or ""),
        }

    def _replace_placeholders_in_presentation(self, prs: Any, values: dict[str, str]) -> None:
        for slide in prs.slides:
            self._replace_placeholders_in_slide(slide, values)

    def _apply_placeholder_sheets(self, wb: Any, placeholder_sheets: list[dict[str, Any]], context: dict[str, str]) -> None:
        from openpyxl.cell.cell import MergedCell
        for sheet_mapper in placeholder_sheets:
            sheet_name = sheet_mapper.get("sheet_name")
            if not sheet_name or sheet_name not in wb.sheetnames:
                continue
            values = build_placeholder_values(sheet_mapper.get("placeholders", {}), source=None, context=context)
            ws = wb[sheet_name]
            for row in ws.iter_rows():
                for cell in row:
                    if isinstance(cell, MergedCell) or not isinstance(cell.value, str):
                        continue
                    text = cell.value
                    for key, value in values.items():
                        text = text.replace(key, value or "")
                    cell.value = text

    def _header_map(self, ws: Any, header_row: int = 1) -> dict[str, int]:
        headers: dict[str, int] = {}
        for cell in ws[header_row]:
            if cell.value is None:
                continue
            key = str(cell.value).replace("\n", "").strip()
            if key and key not in headers:
                headers[key] = cell.column
        return headers

    def _find_column(self, headers: dict[str, int], column_mapper: dict[str, Any]) -> int | None:
        if column_mapper.get("column") is not None:
            return int(column_mapper["column"])
        normalized_headers = {name.replace("\n", "").strip(): col for name, col in headers.items()}
        for name in column_mapper.get("header_names") or []:
            key = str(name).replace("\n", "").strip()
            if key in normalized_headers:
                return normalized_headers[key]
        if column_mapper.get("default_column") is not None:
            return int(column_mapper["default_column"])
        if column_mapper.get("optional"):
            return None
        return None

    def _write_mapped_rows(self, ws: Any, items: list[dict[str, Any]], data_mapper: dict[str, Any], columns: list[dict[str, Any]], context: dict[str, str], source_builder: Any) -> None:
        from copy import copy
        from openpyxl.cell.cell import MergedCell
        header_row = int(data_mapper.get("header_row", 1))
        start_row = int(data_mapper.get("start_row", 2))

        # Requirement templates often contain pre-merged sample rows below the
        # header. If we write generated rows into those merged ranges, only the
        # first row receives values and following rows look blank. Unmerge only
        # the data area, keeping cover/history sheet formatting intact.
        for merged_range in list(ws.merged_cells.ranges):
            if merged_range.max_row >= start_row:
                ws.unmerge_cells(str(merged_range))

        headers = self._header_map(ws, header_row=header_row)
        resolved_columns = []
        for column_mapper in columns:
            col_no = self._find_column(headers, column_mapper)
            if col_no is not None:
                resolved_columns.append((col_no, column_mapper))

        # Ensure there are enough physical rows and copy the first data row style
        # to newly created rows so template formatting remains close to sample_0605.
        required_max_row = start_row + max(len(items), 1) - 1
        if ws.max_row < required_max_row:
            template_row = start_row if ws.max_row >= start_row else header_row
            for row_idx in range(ws.max_row + 1, required_max_row + 1):
                for col_idx in range(1, ws.max_column + 1):
                    src = ws.cell(row=template_row, column=col_idx)
                    dst = ws.cell(row=row_idx, column=col_idx)
                    if src.has_style:
                        dst._style = copy(src._style)
                    dst.number_format = src.number_format
                    dst.alignment = copy(src.alignment)
                    dst.font = copy(src.font)
                    dst.fill = copy(src.fill)
                    dst.border = copy(src.border)

        if data_mapper.get("clear_existing_rows", True):
            for row in range(start_row, ws.max_row + 1):
                for col_no, _ in resolved_columns:
                    cell = ws.cell(row=row, column=col_no)
                    if not isinstance(cell, MergedCell):
                        cell.value = None

        for row_offset, item in enumerate(items):
            excel_row = start_row + row_offset
            row_number = row_offset + 1
            source = source_builder(item)
            for col_no, column_mapper in resolved_columns:
                cell = ws.cell(row=excel_row, column=col_no)
                if isinstance(cell, MergedCell):
                    continue
                cell.value = get_value(source, column_mapper.get("field", ""), context=context, row_number=row_number)

    def _replace_common_slide_placeholders(self, prs: Any, mapper: dict[str, Any], context: dict[str, str]) -> None:
        common_values = build_placeholder_values(get_nested(mapper, "placeholder_slides", "common", default={}) or {}, context=context)
        for slide_index in mapper.get("common_slide_indices", [0, 1]):
            if slide_index < len(prs.slides):
                self._replace_placeholders_in_slide(prs.slides[slide_index], common_values)

    def _replace_placeholders_in_slide(self, slide: Any, values: dict[str, str]) -> None:
        def replace_text(value: str) -> str:
            text = str(value or "")
            for key, replacement in values.items():
                text = text.replace(key, replacement or "")
            return text

        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False):
                original = shape.text or ""
                replaced = replace_text(original)
                # python-pptx may split a placeholder across multiple runs. If
                # the full text changed, assign the whole text frame so split
                # placeholders like {프로젝트명}, {요구사항ID}, {화면ID} are also mapped.
                if replaced != original:
                    shape.text = replaced
                else:
                    for paragraph in shape.text_frame.paragraphs:
                        for run in paragraph.runs:
                            run.text = replace_text(run.text)
            if getattr(shape, "has_table", False):
                for row in shape.table.rows:
                    for cell in row.cells:
                        original = cell.text or ""
                        replaced = replace_text(original)
                        if replaced != original:
                            cell.text = replaced
                        else:
                            for paragraph in cell.text_frame.paragraphs:
                                for run in paragraph.runs:
                                    run.text = replace_text(run.text)

    def _fill_description_table(self, slide: Any, source: dict[str, Any], table_mapper: dict[str, Any]) -> bool:
        display_items = list(source.get(table_mapper.get("display_items_field", "display_items"), []) or [])
        if not display_items:
            display_items = [
                {"item_name": "요구사항ID", "description": source.get("requirement_id", "")},
                {"item_name": "요구사항명", "description": source.get("requirement_name") or source.get("screen_name", "")},
                {"item_name": "Description", "description": source.get("description", "")},
            ]
        else:
            # Ensure the requirement-spec content appears in the description area
            # even when the agent also provides UI display items.
            mandatory = [
                {"item_name": "요구사항ID", "description": source.get("requirement_id", "")},
                {"item_name": "요구사항명", "description": source.get("requirement_name") or source.get("screen_name", "")},
                {"item_name": "Description", "description": source.get("description", "")},
            ]
            seen_names = {str(item.get("item_name", "")).strip() for item in display_items}
            display_items = [item for item in mandatory if str(item.get("item_name", "")).strip() not in seen_names] + display_items

        start_row = int(table_mapper.get("start_row", 1))
        target_column = int(table_mapper.get("target_column", 1))
        max_items = int(table_mapper.get("max_items", 10))
        text_format = table_mapper.get("text_format", "{item_name}: {description}")
        clear_rows = bool(table_mapper.get("clear_rows_before_fill", True))
        for shape in slide.shapes:
            if not getattr(shape, "has_table", False):
                continue
            table = shape.table
            if len(table.columns) <= target_column:
                continue
            if clear_rows:
                for row_idx in range(start_row, len(table.rows)):
                    try:
                        table.cell(row_idx, target_column).text = ""
                    except Exception:
                        pass
            for offset, display_item in enumerate(display_items[:max_items]):
                row_idx = start_row + offset
                if row_idx >= len(table.rows):
                    break
                text = text_format.format(
                    item_name=display_item.get("item_name", ""),
                    description=display_item.get("description", ""),
                )
                table.cell(row_idx, target_column).text = text
            return True
        return False

    def _add_description_fallback(self, slide: Any, source: dict[str, Any]) -> None:
        from pptx.util import Inches, Pt
        text = "\n".join([
            f"요구사항ID: {source.get('requirement_id', '')}",
            f"요구사항명: {source.get('requirement_name') or source.get('screen_name', '')}",
            f"Description: {source.get('description', '')}",
        ]).strip()
        box = slide.shapes.add_textbox(Inches(8.0), Inches(1.15), Inches(4.7), Inches(4.8))
        box.text_frame.text = text
        for paragraph in box.text_frame.paragraphs:
            paragraph.font.size = Pt(11)

    def _get_blank_slide_layout(self, prs: Any) -> Any:
        """Return a usable blank-like slide layout without assuming layout index 6 exists."""
        layouts = list(prs.slide_layouts)
        if not layouts:
            raise ValueError("PPTX template has no slide layouts")
        blank_candidates = [
            layout for layout in layouts
            if "blank" in (getattr(layout, "name", "") or "").lower()
            or "빈" in (getattr(layout, "name", "") or "")
        ]
        if blank_candidates:
            return blank_candidates[0]
        return min(layouts, key=lambda layout: len(getattr(layout, "placeholders", [])))

    def _duplicate_slide(self, prs: Any, template_slide_index: int) -> Any:
        from copy import deepcopy

        source = prs.slides[template_slide_index]
        dest = prs.slides.add_slide(self._get_blank_slide_layout(prs))

        for shape in source.shapes:
            dest.shapes._spTree.insert_element_before(deepcopy(shape.element), "p:extLst")

        # Do not copy slide relationships with python-pptx private APIs.
        # Template slide duplication here only needs editable shapes/tables/text.
        # Copying rels can fail on python-pptx versions where _Relationships
        # has no add_relationship() method, and can also duplicate rIds.
        return dest


    def _delete_slide(self, prs: Any, slide_index: int) -> None:
        xml_slides = prs.slides._sldIdLst
        slides = list(xml_slides)
        if 0 <= slide_index < len(slides):
            xml_slides.remove(slides[slide_index])


    def _style_sheet(self, ws: Any, widths: list[int]) -> None:
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter

        header_fill = PatternFill(fill_type="solid", fgColor="D9EAF7")
        for cell in ws[1]:
            cell.font = Font(bold=True)
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        for row in ws.iter_rows(min_row=2):
            for cell in row:
                cell.alignment = Alignment(vertical="top", wrap_text=True)
        for idx, width in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(idx)].width = width
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

    def _save_workbook(self, workbook: Any) -> bytes:
        bio = BytesIO()
        workbook.save(bio)
        return bio.getvalue()


artifact_export_service = ArtifactExportService()
