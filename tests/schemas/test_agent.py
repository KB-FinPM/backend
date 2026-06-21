import pytest
from pydantic import ValidationError

from app.schemas.agent import AgentRequest


def test_agent_request_accepts_json_serializable_context() -> None:
    request = AgentRequest(
        project_id="PRJ-001",
        context={"target_artifact_type": "REQUIREMENT_SPEC", "items": [1, 2]},
    )

    assert request.context == {
        "target_artifact_type": "REQUIREMENT_SPEC",
        "items": [1, 2],
    }


def test_agent_request_rejects_service_instance_in_context() -> None:
    class ServiceInstance:
        pass

    with pytest.raises(ValidationError):
        AgentRequest(
            project_id="PRJ-001",
            context={"service": ServiceInstance()},
        )
