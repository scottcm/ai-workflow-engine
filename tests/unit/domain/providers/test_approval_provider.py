"""Tests for ApprovalProvider ABC.

TDD Tests for ADR-0012 Phase 3.
"""

import pytest
from abc import ABC

from aiwf.domain.providers.approval_provider import ApprovalProvider


class TestApprovalProviderABC:
    """Tests for ApprovalProvider abstract base class."""

    def test_approval_provider_is_abstract(self) -> None:
        """ApprovalProvider cannot be instantiated directly."""
        with pytest.raises(TypeError):
            ApprovalProvider()  # type: ignore[abstract]

    def test_approval_provider_is_abc(self) -> None:
        """ApprovalProvider inherits from ABC."""
        assert issubclass(ApprovalProvider, ABC)

    def test_approval_provider_has_evaluate_method(self) -> None:
        """ApprovalProvider defines evaluate abstract method."""
        assert hasattr(ApprovalProvider, "evaluate")
        assert getattr(ApprovalProvider.evaluate, "__isabstractmethod__", False)

    def test_approval_provider_has_requires_user_input_property(self) -> None:
        """ApprovalProvider defines requires_user_input abstract property."""
        assert hasattr(ApprovalProvider, "requires_user_input")
        # Check it's an abstract property
        assert isinstance(
            getattr(ApprovalProvider, "requires_user_input"), property
        )