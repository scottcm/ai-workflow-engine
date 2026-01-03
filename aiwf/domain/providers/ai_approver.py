"""Backwards compatibility re-export.

ADR-0015: AIApprovalProvider is now in ai_approval_provider.py
"""

from aiwf.domain.providers.ai_approval_provider import AIApprovalProvider

__all__ = ["AIApprovalProvider"]
