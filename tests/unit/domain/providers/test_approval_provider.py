"""Tests for ApprovalProvider ABC.

ADR-0015: Tests for approval provider abstract base class.
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

    def test_approval_provider_has_get_metadata_method(self) -> None:
        """ApprovalProvider defines get_metadata class method."""
        assert hasattr(ApprovalProvider, "get_metadata")
        metadata = ApprovalProvider.get_metadata()
        assert "name" in metadata
        assert "description" in metadata
        assert "fs_ability" in metadata
