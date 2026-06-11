# EN: LLM service wrapper for Bedrock or future model providers.
# KO: Bedrock 및 향후 모델 제공자를 감싸는 LLM 서비스 래퍼입니다.

from __future__ import annotations

import asyncio
import json
from typing import Any

import boto3
from app.core.config import Settings, settings
from app.core.logger import get_logger

logger = get_logger(__name__)
LLM_LOG_PREFIX = "!!! LLM"


class LLMService:
    """
    모든 Agent는 이 클래스를 통해서만 LLM을 호출합니다.
    Agent에서 boto3 또는 Bedrock 직접 호출 금지.
    """

    def __init__(self):
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=settings.AWS_REGION,
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID or None,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
            verify=settings.AWS_CA_BUNDLE or settings.AWS_VERIFY_SSL,
        )
        self.model_id = ""
        self.model_source = "unset"
        self.default_max_tokens = 4000
        self.total_invocations = 0
        self.successful_invocations = 0
        self.failed_invocations = 0
        self._refresh_model_config()

    def _resolve_model_config(self) -> tuple[str, str]:
        runtime_settings = Settings()
        if runtime_settings.BEDROCK_INFERENCE_PROFILE_ID.strip():
            return runtime_settings.BEDROCK_INFERENCE_PROFILE_ID.strip(), "inference_profile"
        if runtime_settings.BEDROCK_MODEL_ID.strip():
            return runtime_settings.BEDROCK_MODEL_ID.strip(), "model_id"
        raise RuntimeError(
            "Bedrock model identifier is not configured. "
            "Set BEDROCK_INFERENCE_PROFILE_ID or BEDROCK_MODEL_ID in .env."
        )

    def _refresh_model_config(self) -> None:
        self.model_id, self.model_source = self._resolve_model_config()
        logger.info(
            f"{LLM_LOG_PREFIX} config loaded | "
            f"model={self.model_id} | model_source={self.model_source}"
        )

    def _build_request_body(self, prompt: str, system: str = "", max_tokens: int | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": max_tokens or self.default_max_tokens,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt,
                        }
                    ],
                }
            ],
        }
        if system.strip():
            body["system"] = system.strip()
        return body

    async def invoke(self, prompt: str, system: str = "", max_tokens: int | None = None) -> str:
        """
        Bedrock Claude 호출.
        """
        self._refresh_model_config()
        self.total_invocations += 1
        invocation_no = self.total_invocations
        logger.info(
            f"{LLM_LOG_PREFIX} invoke start | "
            f"call={invocation_no} | model={self.model_id} | model_source={self.model_source} | "
            f"max_tokens={max_tokens or self.default_max_tokens}"
        )
        logger.debug(f"prompt preview: {prompt[:100]}...")

        request_body = self._build_request_body(prompt, system=system, max_tokens=max_tokens)

        def _invoke() -> str:
            response = self.client.invoke_model(
                modelId=self.model_id,
                contentType="application/json",
                accept="application/json",
                body=json.dumps(request_body),
            )
            raw_body = response.get("body")
            if raw_body is None:
                return ""
            if hasattr(raw_body, "read"):
                raw_text = raw_body.read().decode("utf-8")
            elif isinstance(raw_body, (bytes, bytearray)):
                raw_text = bytes(raw_body).decode("utf-8")
            else:
                raw_text = str(raw_body)

            payload = json.loads(raw_text) if raw_text else {}
            content = payload.get("content", [])
            if isinstance(content, list):
                parts: list[str] = []
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
                if parts:
                    return "\n".join(parts).strip()
            if isinstance(payload.get("output"), str):
                return payload["output"].strip()
            return raw_text.strip()

        try:
            response_text = await asyncio.to_thread(_invoke)
            self.successful_invocations += 1
            logger.info(
                f"{LLM_LOG_PREFIX} invoke success | "
                f"call={invocation_no} | model={self.model_id} | model_source={self.model_source} | "
                f"successes={self.successful_invocations} | failures={self.failed_invocations} | "
                f"response_chars={len(response_text)}"
            )
            logger.debug(f"{LLM_LOG_PREFIX} response preview | call={invocation_no} | text={response_text[:200]}")
            return response_text
        except Exception as exc:
            self.failed_invocations += 1
            error_text = str(exc)
            logger.error(
                f"{LLM_LOG_PREFIX} invoke failed | model={self.model_id} | "
                f"model_source={self.model_source} | error={error_text}"
            )
            logger.error(
                f"{LLM_LOG_PREFIX} invoke failure stats | "
                f"call={invocation_no} | model={self.model_id} | model_source={self.model_source} | "
                f"successes={self.successful_invocations} | failures={self.failed_invocations}"
            )
            raise RuntimeError(
                f"{error_text} | model_id={self.model_id} | model_source={self.model_source}"
            ) from exc


llm_service = LLMService()
