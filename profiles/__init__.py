"""Workflow profiles package.

Importing this package triggers registration of all profile implementations
with the ProfileFactory.
"""
from aiwf.domain.profiles.profile_factory import ProfileFactory

# Import profile packages to trigger registration
from . import jpa_mt  # noqa: F401

# Register profiles with the factory for non-CLI usage (orchestrator, tests)
ProfileFactory.register("jpa-mt", jpa_mt.JpaMtProfile)
