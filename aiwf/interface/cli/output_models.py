from typing import Any, Literal
from pydantic import BaseModel, Field


class BaseOutput(BaseModel):
    schema_version: int = 1
    command: Literal["init", "step", "status", "approve", "list", "profiles", "providers", "validate"]
    exit_code: int
    error: str | None = None


class InitOutput(BaseOutput):
    command: Literal["init"] = "init"
    # On init errors, session_id may be unknown; omit it from JSON via exclude_none.
    session_id: str | None = None


class StepOutput(BaseOutput):
    command: Literal["step"] = "step"
    session_id: str
    phase: str | None = None
    status: str | None = None
    iteration: int | None = None
    noop_awaiting_artifact: bool = False
    awaiting_paths: list[str] = []
    last_error: str | None = None


class StatusOutput(BaseOutput):
    command: Literal["status"] = "status"
    session_id: str
    phase: str | None = None
    status: str | None = None
    iteration: int | None = None
    session_path: str
    last_error: str | None = None


class ApproveOutput(BaseOutput):
    command: Literal["approve"] = "approve"
    session_id: str
    phase: str | None = None
    status: str | None = None
    approved: bool = False
    hashes: dict[str, str] = Field(default_factory=dict)


class SessionSummary(BaseModel):
    """Summary of a single session for list output."""
    session_id: str
    profile: str
    scope: str
    entity: str
    phase: str
    status: str
    iteration: int
    created_at: str
    updated_at: str


class ListOutput(BaseOutput):
    command: Literal["list"] = "list"
    sessions: list[SessionSummary] = Field(default_factory=list)
    total: int = 0


class ProfileSummary(BaseModel):
    """Summary of a profile for list output."""
    name: str
    description: str
    scopes: list[str] = Field(default_factory=list)
    requires_config: bool = False


class ProfileDetail(BaseModel):
    """Detailed profile info for single profile view."""
    name: str
    description: str
    target_stack: str
    scopes: list[str] = Field(default_factory=list)
    phases: list[str] = Field(default_factory=list)
    requires_config: bool = False
    config_keys: list[str] = Field(default_factory=list)


class ProfilesOutput(BaseOutput):
    command: Literal["profiles"] = "profiles"
    profiles: list[ProfileSummary] | None = None
    profile: ProfileDetail | None = None


class ProviderSummary(BaseModel):
    """Summary of a provider for list output."""
    name: str
    description: str
    requires_config: bool = False


class ProviderDetail(BaseModel):
    """Detailed provider info for single provider view."""
    name: str
    description: str
    requires_config: bool = False
    config_keys: list[str] = Field(default_factory=list)


class ProvidersOutput(BaseOutput):
    command: Literal["providers"] = "providers"
    providers: list[ProviderSummary] | None = None
    provider: ProviderDetail | None = None


class ValidationResult(BaseModel):
    """Result of validating a single provider."""

    provider_type: str  # "ai" or "standards"
    provider_key: str
    passed: bool
    error: str | None = None


class ValidateOutput(BaseOutput):
    """Output for validate command."""

    command: Literal["validate"] = "validate"
    results: list[ValidationResult] = Field(default_factory=list)
    all_passed: bool = True
