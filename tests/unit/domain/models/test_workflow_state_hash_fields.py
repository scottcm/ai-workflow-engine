import pytest
from pydantic import ValidationError

from aiwf.domain.models.workflow_state import ExecutionMode, WorkflowPhase, WorkflowState, WorkflowStatus


def _minimal_workflow_state_kwargs() -> dict:
    return {
        "session_id": "s-1",
        "profile": "jpa_mt",
        "scope": "domain",
        "entity": "Tier",
        "phase": WorkflowPhase.INIT,
        "status": WorkflowStatus.IN_PROGRESS,
        "execution_mode": ExecutionMode.INTERACTIVE,
        "providers": {"planner": "manual", "generator": "manual", "reviewer": "manual", "reviser": "manual"},
        "standards_hash": "sha256:deadbeef",
    }


def test_workflow_state_requires_standards_hash() -> None:
    kwargs = _minimal_workflow_state_kwargs()
    kwargs.pop("standards_hash")
    with pytest.raises(ValidationError):
        WorkflowState(**kwargs)


def test_workflow_state_defaults_plan_approved_false_and_plan_hash_none() -> None:
    ws = WorkflowState(**_minimal_workflow_state_kwargs())
    assert ws.plan_approved is False
    assert ws.plan_hash is None


def test_workflow_state_accepts_plan_hash_when_provided() -> None:
    kwargs = _minimal_workflow_state_kwargs()
    kwargs["plan_hash"] = "sha256:abcd"
    ws = WorkflowState(**kwargs)
    assert ws.plan_hash == "sha256:abcd"
