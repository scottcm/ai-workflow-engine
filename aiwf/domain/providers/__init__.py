from .response_provider import ResponseProvider, AIProvider  # AIProvider is backwards compat alias
from .provider_factory import ProviderFactory
from .manual_provider import ManualProvider

# Register built-in providers
ProviderFactory.register("manual", ManualProvider)

__all__ = ["ResponseProvider", "AIProvider", "ProviderFactory", "ManualProvider"]