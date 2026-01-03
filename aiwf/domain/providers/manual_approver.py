"""Backwards compatibility re-export.

ADR-0015: ManualApprovalProvider is now in approval_provider.py
"""

from aiwf.domain.providers.approval_provider import ManualApprovalProvider

__all__ = ["ManualApprovalProvider"]
