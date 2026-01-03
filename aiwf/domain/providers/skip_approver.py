"""Backwards compatibility re-export.

ADR-0015: SkipApprovalProvider is now in approval_provider.py
"""

from aiwf.domain.providers.approval_provider import SkipApprovalProvider

__all__ = ["SkipApprovalProvider"]
