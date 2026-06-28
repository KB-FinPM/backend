from pathlib import Path

from util import agent_template_utils


def test_resolve_local_template_file_matches_hash_unicode_names(
    tmp_path,
    monkeypatch,
) -> None:
    encoded_file = (
        tmp_path
        / "#Ud0ec#Ud50c#Ub9bf_#Uc694#Uad6c#Uc0ac#Ud56d#Uba85#Uc138#Uc11c.xlsx"
    )
    encoded_file.write_bytes(b"template")

    monkeypatch.setattr(agent_template_utils, "TEMPLATE_DIR", tmp_path)

    resolved = agent_template_utils._resolve_local_template_file(
        "template/탬플릿_요구사항명세서.xlsx"
    )

    assert resolved == encoded_file


def test_resolve_local_template_file_accepts_encoded_request_name(
    tmp_path,
    monkeypatch,
) -> None:
    template_file = tmp_path / "탬플릿_WBS.xlsx"
    template_file.write_bytes(b"template")

    monkeypatch.setattr(agent_template_utils, "TEMPLATE_DIR", tmp_path)

    resolved = agent_template_utils._resolve_local_template_file(
        "template/#Ud0ec#Ud50c#Ub9bf_WBS.xlsx"
    )

    assert resolved == template_file


def test_build_template_context_does_not_use_audit_author_fallbacks() -> None:
    context = agent_template_utils.build_template_context(
        "PRJ-001",
        {
            "created_by": "local-dev-user",
            "user_id": "local_dev_user",
            "requester": "작성자",
        },
    )

    assert context["author"] == ""


def test_build_template_context_uses_explicit_author_only() -> None:
    context = agent_template_utils.build_template_context(
        "PRJ-001",
        {
            "author": " 홍길동 ",
            "writer": "김PM",
            "created_by": "local-dev-user",
        },
    )

    assert context["author"] == "홍길동"
