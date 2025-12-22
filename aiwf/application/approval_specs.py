from dataclasses import dataclass
from typing import Mapping

from aiwf.domain.models.workflow_state import WorkflowPhase


@dataclass(frozen=True, slots=True)
class IngApprovalSpec:
    """Resolver metadata for ING phases where approve calls a provider."""
    provider_role: str  # Key into providers config: planner, generator, reviewer, reviser
    prompt_relpath_template: str
    response_relpath_template: str


@dataclass(frozen=True, slots=True)
class EdApprovalSpec:
    """Resolver metadata for ED phases where 'approve' hashes existing outputs."""

    # Exactly one of these must be non-None for a given phase.
    plan_relpath: str | None = None
    code_dir_relpath_template: str | None = None
    response_relpath_template: str | None = None

    def __post_init__(self) -> None:
        set_count = sum(
            1 for x in (
                self.plan_relpath,
                self.code_dir_relpath_template,
                self.response_relpath_template
            ) if x is not None
        )
        if set_count != 1:
            raise ValueError(
                "EdApprovalSpec requires exactly one of "
                "plan_relpath, code_dir_relpath_template, or response_relpath_template to be set"
            )


# -----------------------------
# ING phases (provider-backed)
# -----------------------------
ING_APPROVAL_SPECS: Mapping[WorkflowPhase, IngApprovalSpec] = {
    WorkflowPhase.PLANNING: IngApprovalSpec(
        provider_role="planner",
        prompt_relpath_template="iteration-1/planning-prompt.md",
        response_relpath_template="iteration-1/planning-response.md",
    ),
    WorkflowPhase.GENERATING: IngApprovalSpec(
        provider_role="generator",
        prompt_relpath_template="iteration-{N}/generation-prompt.md",
        response_relpath_template="iteration-{N}/generation-response.md",
    ),
    WorkflowPhase.REVIEWING: IngApprovalSpec(
        provider_role="reviewer",
        prompt_relpath_template="iteration-{N}/review-prompt.md",
        response_relpath_template="iteration-{N}/review-response.md",
    ),
    WorkflowPhase.REVISING: IngApprovalSpec(
        provider_role="reviser",
        prompt_relpath_template="iteration-{N}/revision-prompt.md",
        response_relpath_template="iteration-{N}/revision-response.md",
    ),
}


# -----------------------------
# ED phases (hash outputs)
# -----------------------------
ED_APPROVAL_SPECS: Mapping[WorkflowPhase, EdApprovalSpec] = {
    WorkflowPhase.PLANNED: EdApprovalSpec(plan_relpath="plan.md"),
    WorkflowPhase.GENERATED: EdApprovalSpec(code_dir_relpath_template="iteration-{N}/code"),
    WorkflowPhase.REVISED: EdApprovalSpec(code_dir_relpath_template="iteration-{N}/code"),
    WorkflowPhase.REVIEWED: EdApprovalSpec(response_relpath_template="iteration-{N}/review-response.md"),
}


def is_ing_approvable(phase: WorkflowPhase) -> bool:
    return phase in ING_APPROVAL_SPECS


def is_ed_approvable(phase: WorkflowPhase) -> bool:
    return phase in ED_APPROVAL_SPECS
