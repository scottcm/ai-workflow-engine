# ADR-0017: Plugin Dependency Injection

**Status:** Proposed
**Date:** January 2026
**Deciders:** Scott

---

## Context and Problem Statement

The current `GateContext` class passes 9 callbacks to approval gate handlers, creating tight coupling between the orchestrator and gate implementations. While functional, this pattern makes testing verbose and adding new capabilities requires modifying the callback signature.

As the system grows, we need a cleaner way to provide services to plugins (profiles, providers, approval handlers) without callback proliferation.

## Decision Drivers

- Reduce callback count in GateContext
- Enable plugins to access services without orchestrator coupling
- Maintain testability with easy mocking
- Avoid over-engineering for current scope

## Considered Options

### Option 1: Full DI Container (Rejected)

Introduce a proper DI container (e.g., `dependency-injector` library) with constructor injection throughout.

**Pros:** Industry standard, excellent testability
**Cons:** Significant refactor, overkill for current codebase size

### Option 2: Service Locator Pattern (Proposed)

Create a `ServiceRegistry` that plugins query for services. Services are registered at startup and retrieved by type.

```python
class ServiceRegistry:
    _services: dict[type, Any] = {}

    @classmethod
    def register(cls, service_type: type, instance: Any) -> None:
        cls._services[service_type] = instance

    @classmethod
    def get(cls, service_type: type[T]) -> T:
        return cls._services[service_type]

# Usage in gate handler
artifact_service = ServiceRegistry.get(ArtifactService)
```

**Pros:** Simple, minimal refactor, good testability
**Cons:** Service locator is sometimes considered an anti-pattern

### Option 3: Context Object with Services (Proposed Alternative)

Expand `GateContext` to hold service references instead of callbacks:

```python
@dataclass
class GateContext:
    state: WorkflowState
    session_path: Path
    services: WorkflowServices  # New: holds ArtifactService, HashService, etc.
```

**Pros:** Incremental change, maintains current patterns
**Cons:** Still requires passing context everywhere

## Decision Outcome

**Deferred.** The current 9-callback approach is acceptable for the existing codebase. This ADR documents the future direction when/if callback proliferation becomes a maintenance burden.

When implemented, Option 2 (Service Locator) or Option 3 (Context with Services) are both viable. The choice depends on whether we want global service access or explicit context passing.

## Consequences

### If Implemented

**Positive:**
- Cleaner plugin interfaces
- Easier to add new services
- Better separation of concerns

**Negative:**
- Migration effort for existing code
- Learning curve for contributors

### Current State (Deferred)

- GateContext maintains 9 callbacks
- Testing requires mocking all callbacks
- Adding new capabilities requires signature changes
- Acceptable trade-off for current scope

## Related

- ADR-0007: Plugin Architecture (current provider/profile plugin system)
- ADR-0012: Phase+Stage model (defines GateContext usage)
- ADR-0015: Approval Provider Implementation (primary consumer of GateContext)
