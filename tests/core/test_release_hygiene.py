from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]


def _git_ls_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.skip("git ls-files is not available")
    return [
        path.replace("\\", "/")
        for path in result.stdout.decode("utf-8", errors="replace").split("\0")
        if path
    ]


def test_git_tracked_files_exclude_secret_and_generated_artifacts() -> None:
    tracked = _git_ls_files()
    forbidden: list[str] = []
    for path in tracked:
        name = Path(path).name
        if path == ".env":
            forbidden.append(path)
        elif name.startswith(".env.") and name != ".env.example":
            forbidden.append(path)
        elif name.endswith((".db", ".sqlite", ".sqlite3", ".log", ".pyc")):
            forbidden.append(path)
        elif any(
            segment in path.split("/")
            for segment in {
                "__pycache__",
                ".pytest_cache",
                ".mock_s3",
                "dist",
                "node_modules",
            }
        ):
            forbidden.append(path)

    assert forbidden == []


def test_env_example_contains_placeholders_only() -> None:
    env_example = REPO_ROOT / ".env.example"
    assert env_example.exists()
    text = env_example.read_text(encoding="utf-8")

    assert not re.search(r"\b(AKIA|ASIA)[0-9A-Z]{16}\b", text)
    assert "-----BEGIN" not in text

    suspicious_assignments: list[str] = []
    allowed_literals = {
        "",
        "true",
        "false",
        "mock",
        "development",
        "ap-northeast-2",
        "sqlite+aiosqlite:///./finpm.db",
        "anthropic.claude-sonnet-4-5",
    }
    secret_keys = re.compile(
        r"(?i)^(AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY|AWS_SESSION_TOKEN|"
        r".*PASSWORD|.*TOKEN|.*SECRET|.*API_KEY|DATABASE_URL)\s*=\s*(.*)$"
    )
    for line in text.splitlines():
        match = secret_keys.match(line.strip())
        if not match:
            continue
        value = match.group(2).strip().strip('"').strip("'")
        if value.lower() in allowed_literals:
            continue
        if value.startswith(("your-", "placeholder", "<")):
            continue
        suspicious_assignments.append(match.group(1))

    assert suspicious_assignments == []


def test_git_tracked_files_do_not_contain_real_looking_credentials() -> None:
    secret_patterns = {
        "aws_access_key_id": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
        "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        "openai_api_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
        "database_url_with_password": re.compile(
            r"(?i)\b(?:postgresql|postgres|mysql|mariadb|mongodb(?:\+srv)?)://"
            r"[^:\s/@]+:[^@\s]+@"
        ),
        "aws_secret_assignment": re.compile(
            r"(?i)\bAWS_(?:SECRET_ACCESS_KEY|SESSION_TOKEN)\s*[:=]\s*"
            r"(?!\s*(?:$|your-|placeholder|<))['\"]?[A-Za-z0-9/+=]{20,}"
        ),
    }
    findings: list[str] = []
    for path in _git_ls_files():
        file_path = REPO_ROOT / path
        if not file_path.is_file():
            continue
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        for pattern_name, pattern in secret_patterns.items():
            if pattern.search(text):
                findings.append(f"{path}:{pattern_name}")

    assert findings == []
