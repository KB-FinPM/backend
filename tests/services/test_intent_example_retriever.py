import pytest

from app.agents.input_agents.chat_input_agent.intent_example_retriever import (
    IntentExampleRetriever,
)
from app.agents.input_agents.chat_input_agent.korean_command_normalizer import (
    KoreanCommandNormalizer,
)


@pytest.mark.anyio
async def test_intent_example_retriever_returns_typo_match_from_curated_examples() -> None:
    normalizer = KoreanCommandNormalizer()
    normalized = normalizer.normalize("회이록에서 액션아이템 뽑아줘").normalized_text
    matches = await IntentExampleRetriever(normalizer=normalizer).retrieve(normalized)

    assert matches
    assert matches[0].example_id == "input.meeting.action_items.001"
    assert matches[0].score >= 0.82
    assert matches[0].intent == "EXTRACT_ACTION_ITEMS"


@pytest.mark.anyio
async def test_intent_example_retriever_keeps_negative_example_guard() -> None:
    normalizer = KoreanCommandNormalizer()
    normalized = normalizer.normalize("회의록 요약해줘").normalized_text
    matches = await IntentExampleRetriever(normalizer=normalizer).retrieve(normalized)

    assert matches
    assert matches[0].polarity == "negative"
    assert matches[0].intent == "GENERAL_QA"


def test_korean_command_normalizer_returns_corrections_metadata() -> None:
    result = KoreanCommandNormalizer().normalize("회의록에서 액션아이탬 뽑아줘")

    assert result.normalized_text == "회의록에서 액션아이템 뽑아줘"
    assert {"source": "액션아이탬", "target": "액션아이템", "type": "typo"} in [
        dict(item) for item in result.corrections
    ]
