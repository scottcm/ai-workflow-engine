# ADR-0010: Profile Access to AI Providers

## Status
Proposed

## Context
Profiles currently operate as pure functions: they receive input (context, response content) and return output (prompts, ProcessingResults with WritePlans). They have no access to AI providers - all provider invocation is handled by the engine's approval handler.

This design keeps profiles testable and predictable, but creates limitations for complex generation scenarios.

### The Vertical Slice Problem
The jpa-mt profile supports "vertical" scope, which generates a complete slice of code:
- Entity + Repository + Service + Controller + DTOs + Mapper + Tests

This can easily be 10+ files. Generating all of them in a single AI call has drawbacks:
- Context window pressure
- Reduced quality per file as the AI splits attention
- All-or-nothing failure mode

Breaking generation into focused calls (entity first, then repo using entity as context, then service...) would produce better results, but currently requires manual mode with external orchestration.

For profiles that want full automation (no user intervention), this isn't an option.

## Decision
Allow profiles to optionally receive an AI provider for internal use during response processing.

### Approach: Optional Provider Parameter
Add an optional `provider` parameter to profile methods that process responses:

```python
def process_generation_response(
    self,
    content: str,
    session_dir: Path,
    iteration: int,
    provider: AIProvider | None = None,  # New optional param
) -> ProcessingResult:
```

Profiles that don't need it ignore the parameter. Profiles that do can use it for:
- Multi-pass generation (build files incrementally)
- Pre-flight validation (lint check before committing)
- Semantic extraction (parse complex responses with AI assistance)
- Code analysis (detect patterns that inform the WritePlan)

### Example: Multi-Pass Vertical Slice Generation
```python
def process_generation_response(
    self,
    content: str,  # Planning response with entity design
    session_dir: Path,
    iteration: int,
    provider: AIProvider | None = None,
) -> ProcessingResult:
    if provider is None:
        # Fall back to single-call behavior
        return self._single_pass_generation(content, session_dir, iteration)

    writes = []
    context = {"plan": content}

    # Generate entity first
    entity_prompt = self._build_entity_prompt(context)
    entity_code = provider.generate(entity_prompt)
    writes.append(WriteOp(path="Entity.java", content=entity_code))
    context["entity"] = entity_code

    # Generate repository with entity context
    repo_prompt = self._build_repo_prompt(context)
    repo_code = provider.generate(repo_prompt)
    writes.append(WriteOp(path="Repository.java", content=repo_code))
    context["repository"] = repo_code

    # Continue building on previous outputs...

    return ProcessingResult(
        status=WorkflowStatus.SUCCESS,
        write_plan=WritePlan(writes=writes),
    )
```

## Consequences

### Positive
- Enables fully automated complex generation scenarios
- Profiles remain testable (pass mock provider in tests)
- Engine still owns provider lifecycle and top-level error handling
- Backward compatible (parameter is optional)
- No new phases or callback machinery needed

### Negative
- Blurs the "profiles don't do I/O" abstraction
- Profile execution time becomes less predictable
- Error handling within profile becomes profile's responsibility
- Debugging multi-call sequences is harder than single calls

### Neutral
- Engine passes the designated provider for the current phase (generator for GENERATING, etc.)
- If profile call to provider fails, profile should return ERROR status or raise
- Provider calls within profile are not individually logged/tracked by engine

## Alternatives Considered

### B: ProcessingResult with AI Check Request
Profile returns a request for AI assistance; engine fulfills it and calls profile again.
- Pro: Keeps profiles pure
- Con: Complex callback/continuation pattern, multiple round-trips

### C: New Sub-Phase for Multi-Step Generation
Add configurable sub-phases (GENERATING_ENTITY, GENERATING_REPO, etc.)
- Pro: Fully engine-controlled, auditable
- Con: Heavy change, rigid, profile-specific phases in engine

## Implementation Notes
- Update `WorkflowProfile` ABC to include optional provider parameter
- Update engine's approval handler to pass provider to profile methods
- Update existing profiles to accept (and ignore) the new parameter
- Add integration test demonstrating multi-pass generation

## Related
- ADR-0001: Architecture overview (Strategy pattern for profiles)
- ADR-0007: AI Provider plugin architecture