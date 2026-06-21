# EN: Shared pytest fixtures for backend tests.
# KO: 백엔드 테스트에서 공유하는 pytest fixture 모음입니다.

from collections.abc import Generator
import os

os.environ["AWS_ACCESS_KEY_ID"] = ""
os.environ["AWS_SECRET_ACCESS_KEY"] = ""
os.environ["AWS_SESSION_TOKEN"] = ""
os.environ["AWS_EC2_METADATA_DISABLED"] = "true"
os.environ["BEDROCK_INFERENCE_PROFILE_ID"] = ""
os.environ["BEDROCK_MODEL_ID"] = "anthropic.claude-sonnet-4-5"

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
