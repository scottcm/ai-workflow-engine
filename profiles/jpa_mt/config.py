"""JPA-MT Profile Configuration Model (v2)."""

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


class StandardsSource(BaseModel):
    """A source for standards files."""

    type: Literal["local", "github"] = "local"
    path: str  # Local path or "owner/repo/path"
    ref: str | None = None  # Branch/tag for github sources


class StandardsConfig(BaseModel):
    """Configuration for standards loading."""

    sources: list[StandardsSource] = Field(default_factory=list)
    cache_dir: Path | None = None
    # Default rules path when sources is empty (None = use profile default location)
    default_rules_path: str | None = None


class ScopeStandardsConfig(BaseModel):
    """Standards configuration for a scope."""

    files: list[str] = Field(default_factory=list)  # Which files to load
    prefixes: list[str] = Field(default_factory=list)  # Rule ID prefixes to include (empty = all)


class ScopeConfig(BaseModel):
    """Configuration for a scope (what to generate and which standards apply)."""

    description: str
    artifacts: list[str]  # e.g., ["entity", "repository"]
    standards: ScopeStandardsConfig = Field(default_factory=ScopeStandardsConfig)


class JpaMtConfig(BaseModel):
    """Root configuration for JPA-MT profile."""

    # Project settings
    base_package: str = "com.example.app"

    # When True, AI makes reasonable assumptions with [ASSUMPTION] tag
    # When False (default), AI stops and asks questions for human to answer
    assume_answers: bool = False

    # AI provider for internal use (prompt regeneration, etc.)
    # When set, profile can use AI for adaptive operations like fixing prompts
    # based on rejection feedback. See ADR-0010.
    ai_provider: str | None = None

    # Standards configuration
    standards: StandardsConfig = Field(default_factory=StandardsConfig)

    # Scope definitions (D6: self-contained, explicit)
    scopes: dict[str, ScopeConfig] = Field(default_factory=lambda: {
        "domain": ScopeConfig(
            description="Entity + Repository",
            artifacts=["entity", "repository"],
            standards=ScopeStandardsConfig(
                files=[
                    "JAVA_STANDARDS_ORG-marked.rules.yml",
                    "NAMING_AND_API-marked.rules.yml",
                    "PACKAGES_AND_LAYERS-marked.rules.yml",
                    "JPA_AND_DATABASE-marked.rules.yml",
                    "ARCHITECTURE_AND_MULTITENANCY-marked.rules.yml",
                ],
                prefixes=["JV-", "JPA-", "PKG-", "DOM-", "NAM-", "MT-"],
            ),
        ),
        "service": ScopeConfig(
            description="Service layer",
            artifacts=["service"],
            standards=ScopeStandardsConfig(
                files=[
                    "JAVA_STANDARDS_ORG-marked.rules.yml",
                    "NAMING_AND_API-marked.rules.yml",
                    "PACKAGES_AND_LAYERS-marked.rules.yml",
                ],
                prefixes=["SVC-"],
            ),
        ),
        "api": ScopeConfig(
            description="Controller + DTO + Mapper",
            artifacts=["controller", "dto", "mapper"],
            standards=ScopeStandardsConfig(
                files=[
                    "JAVA_STANDARDS_ORG-marked.rules.yml",
                    "NAMING_AND_API-marked.rules.yml",
                    "PACKAGES_AND_LAYERS-marked.rules.yml",
                ],
                prefixes=["CTL-", "DTO-", "MAP-", "API-"],
            ),
        ),
        "full": ScopeConfig(
            description="All artifacts",
            artifacts=["entity", "repository", "service", "controller", "dto", "mapper"],
            standards=ScopeStandardsConfig(
                files=[
                    "JAVA_STANDARDS_ORG-marked.rules.yml",
                    "NAMING_AND_API-marked.rules.yml",
                    "PACKAGES_AND_LAYERS-marked.rules.yml",
                    "JPA_AND_DATABASE-marked.rules.yml",
                    "ARCHITECTURE_AND_MULTITENANCY-marked.rules.yml",
                ],
                prefixes=[],  # Empty = all rules
            ),
        ),
    })

    @classmethod
    def from_yaml(cls, path: Path) -> "JpaMtConfig":
        """Load config from YAML file."""
        import yaml

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return cls.model_validate(data or {})
