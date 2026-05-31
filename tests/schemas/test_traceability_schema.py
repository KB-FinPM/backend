# EN: Tests for artifact traceability schema contracts.
# KO: 산출물 추적 관계 스키마 계약 테스트입니다.

import pytest
from pydantic import ValidationError

from app.schemas.traceability import ArtifactLinkCreate, ArtifactRelationType


def test_artifact_link_create_accepts_derived_relation() -> None:
    link = ArtifactLinkCreate(
        project_id="PRJ-001",
        source_artifact_id="ART-REQ-001",
        source_item_id="RQ-001",
        target_artifact_id="ART-WBS-001",
        target_item_id="WBS-001",
        relation_type=ArtifactRelationType.DECOMPOSED_TO,
    )

    assert link.relation_type == ArtifactRelationType.DECOMPOSED_TO


def test_artifact_link_create_rejects_same_source_and_target_item() -> None:
    with pytest.raises(ValidationError):
        ArtifactLinkCreate(
            project_id="PRJ-001",
            source_artifact_id="ART-REQ-001",
            source_item_id="RQ-001",
            target_artifact_id="ART-REQ-001",
            target_item_id="RQ-001",
            relation_type=ArtifactRelationType.REFERENCES,
        )
