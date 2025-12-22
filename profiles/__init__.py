"""Workflow profiles package.

Importing this package triggers registration of all profile implementations
with the ProfileFactory.
"""

# Import profile packages to trigger registration
from . import jpa_mt  # noqa: F401
