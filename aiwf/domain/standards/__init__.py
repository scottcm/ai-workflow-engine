"""Standards provider abstractions and implementations."""

from aiwf.domain.standards.standards_provider_factory import (
    StandardsProvider,
    StandardsProviderFactory,
)
from aiwf.domain.standards.scoped_layer_fs_provider import ScopedLayerFsProvider

# Register built-in standards providers
StandardsProviderFactory.register("scoped-layer-fs", ScopedLayerFsProvider)

__all__ = ["StandardsProvider", "StandardsProviderFactory", "ScopedLayerFsProvider"]