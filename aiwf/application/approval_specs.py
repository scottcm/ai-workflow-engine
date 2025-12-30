"""Approval specs - STUB for ADR-0012 rewrite.

This module is being replaced by the TransitionTable in Phase 2.
These stubs allow existing code to import without error during the transition.
"""

from dataclasses import dataclass
from typing import Any, Mapping

from aiwf.domain.models.workflow_state import WorkflowPhase


@dataclass(frozen=True, slots=True)
class IngApprovalSpec:
    """STUB - Will be replaced by TransitionTable."""

    provider_role: str
    prompt_relpath_template: str
    response_relpath_template: str


@dataclass(frozen=True, slots=True)
class EdApprovalSpec:
    """STUB - Will be replaced by TransitionTable."""

    plan_relpath: str | None = None
    code_dir_relpath_template: str | None = None
    response_relpath_template: str | None = None


# STUB: Empty mappings during transition
ING_APPROVAL_SPECS: Mapping[WorkflowPhase, IngApprovalSpec] = {}
ED_APPROVAL_SPECS: Mapping[WorkflowPhase, EdApprovalSpec] = {}


def is_ing_approvable(phase: WorkflowPhase) -> bool:
    """STUB - Returns False during transition."""
    return False


def is_ed_approvable(phase: WorkflowPhase) -> bool:
    """STUB - Returns False during transition."""
    return False
