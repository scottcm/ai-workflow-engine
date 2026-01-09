"""Approval gate service for workflow orchestration.

Phase 2 of orchestrator modularization: extract approval gating logic.
"""

from .approval_gate_service import (
    ApprovalGateService,
    GateContext,
    _RegenerationNotImplemented,
)

__all__ = ["ApprovalGateService", "GateContext", "_RegenerationNotImplemented"]