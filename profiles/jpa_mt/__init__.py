"""JPA Multi-Tenant Profile package."""

from aiwf.domain.profiles.profile_factory import ProfileFactory
from .jpa_mt_profile import JpaMtProfile
from .template_renderer import TemplateRenderer

# Register profile with factory
ProfileFactory.register("jpa-mt", JpaMtProfile)

__all__ = ["JpaMtProfile", "TemplateRenderer"]