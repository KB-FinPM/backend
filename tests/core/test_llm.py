# EN: Tests for the Bedrock LLM service wrapper.
# KO: Bedrock LLM 서비스 래퍼 테스트입니다.

import json

import pytest

from app.core.llm import LLMService, llm_service


class DummyBody:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class DummyClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def invoke_model(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "body": DummyBody(
                {
                    "content": [
                        {
                            "type": "text",
                            "text": "LLM 응답",
                        }
                    ]
                }
            )
        }


def test_llm_service_builds_bedrock_request_body() -> None:
    service = LLMService()

    body = service._build_request_body("hello", system="sys", max_tokens=123)

    assert body["anthropic_version"] == "bedrock-2023-05-31"
    assert body["max_tokens"] == 123
    assert body["system"] == "sys"
    assert body["messages"][0]["role"] == "user"
    assert body["messages"][0]["content"][0]["text"] == "hello"


@pytest.mark.anyio
async def test_llm_service_invokes_bedrock_and_parses_text(monkeypatch) -> None:
    dummy_client = DummyClient()
    monkeypatch.setattr(llm_service, "client", dummy_client)
    before_total = llm_service.total_invocations
    before_success = llm_service.successful_invocations
    before_failure = llm_service.failed_invocations

    response = await llm_service.invoke("hello", system="sys", max_tokens=321)

    assert response == "LLM 응답"
    assert llm_service.total_invocations == before_total + 1
    assert llm_service.successful_invocations == before_success + 1
    assert llm_service.failed_invocations == before_failure
    assert len(dummy_client.calls) == 1
    call = dummy_client.calls[0]
    assert call["modelId"] == llm_service.model_id
    assert call["contentType"] == "application/json"
    assert call["accept"] == "application/json"

    payload = json.loads(call["body"])
    assert payload["max_tokens"] == 321
    assert payload["system"] == "sys"
    assert payload["messages"][0]["content"][0]["text"] == "hello"
