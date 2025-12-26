# ADR-0009: Prompt Structure and AI Provider Capabilities

**Status:** Draft
**Date:** December 26, 2024
**Deciders:** Scott

---

## Context and Problem Statement

ADR-0007 establishes that AI providers are plugins that define HOW LLMs are invoked. This ADR addresses a deeper question: **What structure should prompts have, and how should providers optimize for their specific LLMs?**

Currently, the engine generates a single text block (prompt file) that gets sent to the AI. This works for manual copy/paste but leaves optimization opportunities on the table for API-based providers.

### Key Questions

1. How should prompts be structured to enable provider optimization?
2. How do providers signal their capabilities to profiles?
3. Who owns generation parameters (tokens, temperature)?
4. How is conversation history managed for multi-turn interactions?
5. Who owns prompt rendering vs. API-specific formatting?

---

## Decision Drivers

1. Profiles should not know about LLM-specific features
2. Profiles own generation parameters (they know what they need)
3. API providers should be able to optimize (system prompts, structured output, etc.)
4. Manual mode must remain first-class (single readable text block)
5. Engine owns file I/O; providers don't write files
6. Conversation history should support multi-turn within a phase if needed

---

## The Core Tension

| Mode | Capabilities | Constraints |
|------|--------------|-------------|
| **API (Claude, GPT)** | System prompt, message history, structured output, streaming | Stateless per call, token limits |
| **CLI Agent (Claude Code, Aider)** | Persistent context, file access, tool use | Less control over prompt structure |
| **Manual (Copy/Paste)** | Human judgment, any LLM | Single text block, no programmatic control |

A single text block works everywhere but is the **lowest common denominator**.

---

## Proposed Solution: PromptBundle + PromptAdapter

### GenerationParams (Profile Controls)

Generation parameters are **profile concerns** - the profile knows what it needs for each phase:

```python
from pydantic import BaseModel

class GenerationParams(BaseModel):
    """Parameters for AI generation. Profile sets these."""

    max_input_tokens: int | None = None     # Max tokens for prompt
    max_output_tokens: int | None = None    # Max tokens for response
    temperature: float | None = None         # 0.0-1.0, creativity vs precision
```

### Profile Configuration

Profiles define generation parameters per phase in their config:

```yaml
# profiles/jpa-mt/config.yml
name: jpa-mt
scopes:
  entity:
    layers: [domain, repository]
  vertical-slice:
    layers: [domain, repository, service, controller]

# Generation parameters per phase
generation_params:
  planning:
    max_input_tokens: 50000
    max_output_tokens: 4000
    temperature: 0.7          # More creative for planning
  generating:
    max_input_tokens: 100000  # Full standards + plan + context
    max_output_tokens: 16000  # Full code output
    temperature: 0.3          # Precise for code
  reviewing:
    max_input_tokens: 100000
    max_output_tokens: 2000   # Just verdict + feedback
    temperature: 0.3
  revising:
    max_input_tokens: 100000
    max_output_tokens: 16000
    temperature: 0.3

# Scope-specific overrides (optional)
scope_overrides:
  vertical-slice:
    generating:
      max_output_tokens: 32000  # More layers = more code
```

### PromptBundle (Engine Defines)

The engine defines a structured prompt object that separates concerns:

```python
from pydantic import BaseModel, Field
from typing import Any

class Message(BaseModel):
    """A single message in conversation history."""
    role: str                    # "user", "assistant", "system"
    content: str

class PromptBundle(BaseModel):
    """Structured prompt that providers can optimize."""

    # Core prompt components
    system_context: str          # Standards, role definition, constraints
    request: str                 # The actual task/question
    output_instructions: str     # Expected format, structure requirements

    # Generation parameters (profile sets these)
    generation_params: GenerationParams | None = None

    # Optional components
    examples: list[str] = Field(default_factory=list)  # Few-shot examples
    conversation_history: list[Message] = Field(default_factory=list)

    # Profile tracking data (NOT sent to AI)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### Metadata Definition

Metadata is profile-specific tracking data used during prompt generation and response processing, **not sent to the AI**:

```python
metadata = {
    "output_directory": "src/main/java/com/example",
    "entity_name": "Customer",
    "target_files": ["Customer.java", "CustomerRepository.java"],
    "iteration": 1,
    "scope": "entity",
}
```

### PromptAdapter (Provider Implements)

Each provider implements an adapter that knows how to:
1. Render the bundle as readable text (for prompt files, manual mode)
2. Convert to API-specific format (for automated calls)

```python
from abc import ABC, abstractmethod

class PromptAdapter(ABC):
    """Adapts PromptBundle to provider-specific formats."""

    @abstractmethod
    def render_for_display(self, bundle: PromptBundle) -> str:
        """
        Render as human-readable text.
        Used for: prompt files, manual mode, logging.
        """
        ...


class ClaudeAdapter(PromptAdapter):
    """Adapter for Claude API."""

    def render_for_display(self, bundle: PromptBundle) -> str:
        """Render as single text block for prompt file."""
        parts = []
        parts.append("## Context and Standards\n")
        parts.append(bundle.system_context)
        parts.append("\n\n## Request\n")
        parts.append(bundle.request)
        parts.append("\n\n## Output Requirements\n")
        parts.append(bundle.output_instructions)
        return "\n".join(parts)

    def to_api_request(self, bundle: PromptBundle) -> dict:
        """Convert to Claude API format."""
        messages = []

        # Add conversation history
        for msg in bundle.conversation_history:
            messages.append({"role": msg.role, "content": msg.content})

        # Add current request
        user_content = f"{bundle.request}\n\n{bundle.output_instructions}"
        messages.append({"role": "user", "content": user_content})

        # Use profile's generation params
        params = bundle.generation_params or GenerationParams()

        return {
            "system": bundle.system_context,
            "messages": messages,
            "max_tokens": params.max_output_tokens or 4096,
            "temperature": params.temperature or 0.5,
        }


class ManualAdapter(PromptAdapter):
    """Adapter for manual copy/paste mode."""

    def render_for_display(self, bundle: PromptBundle) -> str:
        """Render as single comprehensive text block."""
        parts = []

        parts.append("# AI Code Generation Request\n")
        parts.append("## Standards and Context\n")
        parts.append(bundle.system_context)
        parts.append("\n---\n")
        parts.append("## Your Task\n")
        parts.append(bundle.request)
        parts.append("\n---\n")
        parts.append("## Output Format\n")
        parts.append(bundle.output_instructions)

        if bundle.examples:
            parts.append("\n---\n")
            parts.append("## Examples\n")
            for i, example in enumerate(bundle.examples, 1):
                parts.append(f"### Example {i}\n{example}\n")

        return "\n".join(parts)
```

---

## Provider Capabilities

Provider capabilities are **constraints** - hard limits the provider cannot exceed:

```python
class ProviderCapabilities(BaseModel):
    """What this provider supports. These are constraints, not settings."""

    # Token limits (hard limits)
    max_context_tokens: int | None = None      # None = unlimited/unknown
    max_output_tokens: int | None = None

    # Feature support
    supports_system_prompt: bool = True
    supports_structured_output: bool = False   # JSON mode
    supports_streaming: bool = False
    supports_multi_turn: bool = True
    supports_tool_use: bool = False
    supports_temperature: bool = True
    min_temperature: float = 0.0
    max_temperature: float = 1.0

    # Model info
    model_id: str | None = None                # e.g., "claude-3-opus-20240229"
    model_family: str | None = None            # e.g., "claude", "gpt", "gemini"
```

Capabilities are **per-instance** since each provider instance is configured with a specific model:

```python
class AIProvider(ABC):
    def get_capabilities(self) -> ProviderCapabilities:
        """Return capabilities for this provider instance."""
        ...
```

### Profile Respects Provider Limits

Profiles can query capabilities to respect provider limits:

```python
def generate_planning_prompt(
    self,
    context: dict,
    provider_capabilities: ProviderCapabilities
) -> PromptBundle:

    # Get profile's desired params for this phase
    params = self.config.generation_params["planning"]

    # Respect provider's hard limits
    if provider_capabilities.max_output_tokens:
        params.max_output_tokens = min(
            params.max_output_tokens,
            provider_capabilities.max_output_tokens
        )

    # Adapt content based on token limits
    if (provider_capabilities.max_context_tokens and
        provider_capabilities.max_context_tokens < 100000):
        standards = self.get_condensed_standards()
    else:
        standards = self.get_full_standards()

    return PromptBundle(
        system_context=standards,
        request=self.build_request(context),
        output_instructions=self.get_output_format(),
        generation_params=params,
        metadata={"entity": context["entity"], ...}
    )
```

---

## Responsibility Summary

| Concern | Owner | Example |
|---------|-------|---------|
| What tokens/temperature to **request** | Profile (via config) | `max_output_tokens: 16000` |
| What tokens/temperature are **supported** | Provider (via capabilities) | `max_output_tokens: 200000` |
| Actual values **used** | Profile sets, provider respects or adapts | Profile asks for 16000, provider uses 16000 |
| How to **format** for the API | Provider (via adapter) | System prompt, messages array |
| How to **render** for humans | Provider (via adapter) | Single markdown block |

---

## Conversation History

### Storage Location

Conversation history is stored per-phase within each iteration:

```
<session>/
  iteration-1/
    planning-prompt.md           # Rendered PromptBundle (human-readable)
    planning-response.md         # AI response
    planning-conversation.json   # Structured conversation state (optional)
    generation-prompt.md
    generation-response.md
  iteration-2/
    revision-prompt.md
    revision-response.md
    revision-conversation.json   # Multi-turn revision dialogue
```

### Responsibility Split

| Component | Responsibility |
|-----------|----------------|
| **Engine** | Writes all files, loads/passes conversation state |
| **Provider** | Structures conversation state, decides what to include |
| **Profile** | Doesn't manage history directly; sees it in PromptBundle if provider adds it |

### Provider Response Structure

```python
class ProviderResponse(BaseModel):
    """What provider returns after generation."""

    content: str                              # The actual response text
    conversation_state: dict | None = None    # Provider-specific state for multi-turn
    usage: dict | None = None                 # Token usage, timing, etc.
```

The engine:
1. Saves `content` to response file
2. Saves `conversation_state` to conversation.json if present
3. Passes `conversation_state` back to provider on next call (if multi-turn)

---

## Model Selection

Model selection is **provider configuration**, not per-request:

```python
# Provider configured with specific model
claude_opus = ClaudeProvider(model="claude-3-opus-20240229")
claude_sonnet = ClaudeProvider(model="claude-3-5-sonnet-20241022")

# Different providers for different roles
providers = {
    "planner": "claude-sonnet",     # Fast, cheaper for planning
    "generator": "claude-opus",     # Best quality for code generation
    "reviewer": "claude-sonnet",    # Fast for review
    "reviser": "claude-opus",       # Quality for revisions
}
```

This keeps the interface simple while allowing model flexibility.

---

## Updated AIProvider Interface

Incorporating all the above:

```python
from abc import ABC, abstractmethod
from typing import Any

class AIProvider(ABC):
    """Base class for AI providers."""

    @classmethod
    @abstractmethod
    def get_metadata(cls) -> dict[str, Any]:
        """Return provider metadata including timeouts."""
        ...

    @abstractmethod
    def get_capabilities(self) -> ProviderCapabilities:
        """Return capabilities for this provider instance."""
        ...

    @abstractmethod
    def get_adapter(self) -> PromptAdapter:
        """Return the prompt adapter for this provider."""
        ...

    @abstractmethod
    def validate(self) -> None:
        """Verify provider is accessible. Raises ProviderError if not."""
        ...

    @abstractmethod
    def generate(
        self,
        bundle: PromptBundle,
        conversation_state: dict | None = None,
        timeout: int | None = None,
    ) -> ProviderResponse:
        """
        Generate AI response for the given prompt bundle.

        Args:
            bundle: Structured prompt with generation_params
            conversation_state: Prior state for multi-turn (from previous response)
            timeout: Response timeout in seconds

        Returns:
            ProviderResponse with content and optional conversation state

        Raises:
            ProviderError: On failure (network, auth, timeout, etc.)
        """
        ...
```

### ManualProvider Special Case

```python
class ManualProvider(AIProvider):
    """Provider for manual copy/paste mode."""

    def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            max_context_tokens=None,        # Unlimited (human decides)
            max_output_tokens=None,         # Unlimited
            supports_system_prompt=False,   # Single text block
            supports_multi_turn=False,      # No conversation tracking
            supports_temperature=False,     # Human controls this
        )

    def generate(
        self,
        bundle: PromptBundle,
        conversation_state: dict | None = None,
        timeout: int | None = None,
    ) -> ProviderResponse | None:
        # Returns None to signal "user will provide response"
        return None
```

---

## Information Flow

### Current Flow (Single Text Block)

```
Profile.generate_prompt()
    → returns: str (big text block)

Engine
    → writes: prompt file
    → calls: provider.generate(prompt_text)

Provider
    → receives: str
    → sends to LLM however it wants
    → returns: str
```

### Proposed Flow (Structured Bundle)

```
Profile.generate_prompt(context, capabilities)
    → returns: PromptBundle (with generation_params from config)

Engine
    → gets adapter: provider.get_adapter()
    → renders: adapter.render_for_display(bundle)
    → writes: prompt file (human-readable)
    → calls: provider.generate(bundle, conversation_state)

Provider
    → receives: PromptBundle with generation_params
    → converts: adapter.to_api_request(bundle) (internal)
    → sends to LLM with optimal formatting + params
    → returns: ProviderResponse

Engine
    → writes: response file
    → writes: conversation.json (if state returned)
```

---

## Backward Compatibility

### Existing Profiles

Profiles currently return `str` from prompt generation. Migration path:

**Phase 1:** Support both
```python
# Engine checks return type
result = profile.generate_planning_prompt(context)
if isinstance(result, str):
    # Legacy: wrap in minimal bundle
    bundle = PromptBundle(
        system_context="",
        request=result,
        output_instructions="",
    )
else:
    bundle = result
```

**Phase 2:** Deprecate string return, require PromptBundle

### Existing Providers

Only `ManualProvider` exists. Update is straightforward.

---

## Implementation Phases

### Phase 1: Core Infrastructure

1. Define `GenerationParams`, `PromptBundle`, `Message`, `ProviderCapabilities`, `ProviderResponse` models
2. Define `PromptAdapter` protocol
3. Update `AIProvider` interface to use `PromptBundle`
4. Implement `ManualAdapter`
5. Update engine to render bundle to prompt file

### Phase 2: Profile Config

1. Add `generation_params` section to profile config schema
2. Add `scope_overrides` support
3. Update profiles to return `PromptBundle` with params
4. Pass `ProviderCapabilities` to profile prompt generation

### Phase 3: Conversation Support

1. Add conversation.json storage
2. Pass conversation state through provider interface
3. Implement multi-turn for revision phase (if needed)

---

## Risk Assessment

### Risk 1: Over-Engineering

**Risk:** PromptBundle adds complexity without clear benefit until API providers exist.
**Mitigation:** ManualAdapter ensures current workflow still works. Complexity is isolated.
**Severity:** Low

### Risk 2: Capability Mismatch

**Risk:** Profile requests params that provider can't satisfy.
**Mitigation:** `ProviderCapabilities` provides hard limits. Profiles check before setting params.
**Severity:** Low

### Risk 3: Conversation State Bloat

**Risk:** Conversation history grows unbounded.
**Mitigation:** Provider controls what goes in state. Can summarize or truncate.
**Severity:** Medium

### Risk 4: Config Complexity

**Risk:** Per-phase and per-scope params create complex config.
**Mitigation:** Sensible defaults; scope_overrides are optional.
**Severity:** Low

---

## Related Decisions

- ADR-0007: Plugin Architecture (provider as plugin)
- ADR-0005: Chain of Responsibility for Approval (where generate() is called)
- ADR-0006: Observer Pattern for Events (emit events on provider failure)

---

## Decisions Made

| Question | Decision | Rationale |
|----------|----------|-----------|
| Phase in PromptBundle | No | Provider knows its role from configuration |
| Capabilities scope | Per-instance | Matches how providers are configured with specific models |
| Generation params owner | Profile | Profile knows what it needs per phase/scope |
| File attachments | Defer | Current workflow is text-only |

---

## Open Questions

1. How should streaming responses be handled (future)?
2. Should generation_params support additional LLM-specific fields (top_p, etc.)?