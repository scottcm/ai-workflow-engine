# Enhancement: Cross-Entity Workflow Memory

**Status:** Future Enhancement (Post-MVP)  
**Priority:** High (solves real pain point for multi-table projects)  
**Complexity:** Medium  
**Estimated Effort:** 1-2 weeks

---

## Problem Statement

When generating code for multiple related database tables (e.g., 20+ tables in a bounded context), each workflow session operates in isolation. The AI has no awareness of:

- What entities have already been generated
- How tables relate to each other
- Established naming conventions and patterns
- The overall project structure

**Result:** Inconsistent naming, missed relationships, duplicated patterns, loss of architectural coherence across the bounded context.

**Real-world example:** Generating vertical stacks for a control plane bounded context (20+ tables). Currently, generating `Order` entity has no knowledge that `Client` and `Product` entities already exist, leading to inconsistent relationship modeling.

---

## Proposed Solution

Implement a **persistent memory system** that maintains project-level context across multiple workflow sessions.

### Core Concept

A shared memory file tracks:
1. **Project scope** - All entities in the bounded context
2. **Completed work** - Which entities have been generated
3. **Pending work** - What still needs generation
4. **Cross-entity context** - Relationships, naming conventions, shared patterns
5. **Established decisions** - Package structure, patterns, conventions

Each workflow session:
1. Reads memory at start (understands existing context)
2. Generates code with awareness of other entities
3. Updates memory with new entity and decisions
4. Next session picks up with enhanced context

---

## Key Benefits

### 1. **Consistency Across Entities**
- All entities use same naming conventions (clientId vs client_id)
- Consistent package structure
- Uniform service and controller patterns

### 2. **Relationship Awareness**
```java
// WITH memory: AI knows Client entity exists
@ManyToOne(fetch = FetchType.LAZY)
@JoinColumn(name = "client_id")
private Client client;

// WITHOUT memory: AI might do this
private Long clientId;  // Loses type safety and navigability
```

### 3. **Progressive Building**
- Table 1 establishes patterns
- Tables 2-N follow those patterns automatically
- Architectural decisions propagate naturally

### 4. **Resumability**
- If generation fails on table 15 of 23
- Memory shows what's complete, what's pending
- Resume without regenerating previous tables

---

## Memory Structure

**File:** `.aiwf/sessions/{session-id}/project-memory.json`

```json
{
  "project": {
    "name": "Control Plane Bounded Context",
    "total_entities": 23,
    "completed": 5,
    "pending": 18
  },
  "entities": [
    {
      "name": "Client",
      "table": "app.clients",
      "status": "complete",
      "package": "com.example.domain.client",
      "classification": "tenant_entity",
      "relationships": ["hasMany:Product", "hasMany:Order"]
    },
    {
      "name": "Product",
      "table": "app.products", 
      "status": "complete",
      "classification": "tenant_scoped",
      "relationships": ["belongsTo:Client", "belongsTo:Tier"]
    }
  ],
  "conventions": {
    "tenant_field": "clientId",
    "repository_base": "JpaRepository",
    "all_entities_extend": "BaseEntity"
  }
}
```

---

## How It Works

### Session N: Generate Product Entity

**Memory injected into prompt:**
```markdown
## Project Context

You are generating entity 2 of 23 in the Control Plane bounded context.

**Already completed:**
- Client (tenant entity, app.clients)

**Current entity:** Product
- Table: app.products
- Tenant-scoped (has client_id FK)
- Relationships: belongsTo Client

**Established conventions:**
- Tenant field name: clientId
- All entities extend: BaseEntity

Generate Product.java following these established patterns.
```

**After generation, memory is updated:**
```json
{
  "completed": 2,
  "entities": [
    {
      "name": "Product",
      "status": "complete",
      "files_generated": ["Product.java", "ProductRepository.java"]
    }
  ]
}
```

### Session N+1: Generate Order Entity

**Memory now includes:**
- Client (complete)
- Product (complete)
- Order can reference both with confidence

---

## Implementation Approach

### Phase 1: Core Memory System (1 week)
1. Define memory schema (JSON structure)
2. Create `ProjectMemory` model (Pydantic)
3. Implement `MemoryManager` class (load/save/update)
4. Add memory initialization to session creation
5. Unit tests for memory operations

### Phase 2: Integration (1 week)
1. Inject memory context into templates (`{{include: _project_memory}}`)
2. Update `TemplateRenderer` to resolve memory includes
3. Update memory after each successful generation
4. Add memory display to `aiwf status` command
5. Integration tests for multi-entity workflows

### Phase 3: Enhancements (Future)
- Memory visualization (dependency graph)
- Memory validation (detect inconsistencies)
- Memory export/import (share across sessions)
- Multi-bounded-context support

---

## Technical Considerations

### Memory Scope
- **Session-specific** (default) - Memory per session
- **Project-wide** (future) - Memory across sessions for same project

### Memory Format
- **JSON** (compact, single-line for token efficiency)
- Machine-readable (Python `json` module)
- LLM-friendly (standard format in training data)

### Token Usage
- Typical memory: 200-500 tokens
- Negligible cost compared to generation (~10K tokens)
- Huge benefit: consistency worth the small token overhead

### Concurrency
- Single-threaded workflow (no concurrent generations)
- No locking needed for MVP
- Future: Add optimistic locking if needed

---

## Success Metrics

### Before Memory (Current State)
- 23 entities generated independently
- Inconsistent naming across entities
- Missed or incorrect relationships
- Manual consistency fixes required
- ~30% of entities need revision for consistency

### After Memory (Target State)
- 23 entities aware of each other
- Consistent naming and patterns
- Correct relationships on first generation
- Minimal manual fixes needed
- <10% revision rate

---

## Related Enhancements

This feature enables:
- **Batch generation** - Generate all entities in bounded context
- **Dependency-aware ordering** - Generate base entities first
- **Incremental updates** - Add new entities to existing context
- **Multi-profile projects** - Different profiles sharing memory

---

## Dependencies

### Requires (from MVP):
- ✅ Session persistence (`SessionStore`)
- ✅ Template rendering (`TemplateRenderer`)
- ✅ Include resolution (`{{include:}}` directives)

### Enables (future features):
- Batch workflow orchestration
- Multi-table planning phase
- Dependency graph visualization
- Cross-entity validation

---

## Questions to Resolve Before Implementation

1. **Memory scope:** Session-specific or project-wide?
2. **Memory lifecycle:** When to create, update, archive?
3. **Memory size limits:** Max entities per memory file?
4. **Failure handling:** What if memory update fails mid-generation?
5. **Memory evolution:** How to handle schema changes as feature evolves?

---

## Architectural Placement

### Domain Layer
```
aiwf/domain/memory/
```

With:
```markdown
### Domain Layer
```
aiwf/domain/models/
├── project_memory.py        # ProjectMemory model (Pydantic)
├── memory_manager.py        # Load/save/update operations
└── __init__.py
```

### Template Integration
```
profiles/jpa_mt/templates/
├── _shared/
│   └── project-context.md   # Template fragment for memory injection
└── planning/
    └── domain.md            # Updated to include {{include: _project_memory}}
```

### Session Structure
```
.aiwf/sessions/{session-id}/
├── session.json             # Existing - workflow state
├── project-memory.json      # New - cross-entity memory
└── iteration-N/
    └── ...
```

---

## API Design

### ProjectMemory Model
```python
from pydantic import BaseModel, Field
from typing import Literal

class EntityInfo(BaseModel):
    """Information about a generated entity."""
    name: str
    table: str
    status: Literal["pending", "in_progress", "complete", "failed"]
    package: str | None = None
    classification: Literal["tenant_entity", "tenant_scoped", "global"] | None = None
    relationships: list[str] = Field(default_factory=list)
    files_generated: list[str] = Field(default_factory=list)

class ProjectMemory(BaseModel):
    """Persistent memory for multi-entity projects."""
    project_name: str
    total_entities: int
    completed: int = 0
    pending: int = 0
    entities: list[EntityInfo] = Field(default_factory=list)
    conventions: dict[str, str] = Field(default_factory=dict)
    shared_patterns: dict[str, str] = Field(default_factory=dict)
```

### MemoryManager
```python
class MemoryManager:
    """Manages project memory persistence and updates."""
    
    def __init__(self, session_dir: Path):
        self.session_dir = session_dir
        self.memory_file = session_dir / "project-memory.json"
    
    def load(self) -> ProjectMemory:
        """Load memory from file."""
        ...
    
    def save(self, memory: ProjectMemory) -> None:
        """Save memory to file."""
        ...
    
    def update_entity_status(
        self, 
        entity_name: str, 
        status: str,
        files_generated: list[str] | None = None
    ) -> None:
        """Update status of an entity."""
        ...
    
    def add_convention(self, key: str, value: str) -> None:
        """Add a naming convention."""
        ...
    
    def get_context_for_entity(self, entity_name: str) -> str:
        """Generate markdown context for entity generation."""
        ...
```

---

## Testing Strategy

### Unit Tests
- `test_project_memory_model.py` - Pydantic model validation
- `test_memory_manager.py` - Load/save/update operations
- `test_memory_context_generation.py` - Context markdown generation

### Integration Tests
- `test_multi_entity_workflow.py` - Generate 3 entities with memory
- `test_memory_persistence.py` - Memory survives across sessions
- `test_relationship_awareness.py` - Later entities reference earlier ones

### End-to-End Tests
- Generate 5-table bounded context
- Verify consistent naming across all entities
- Verify correct relationship modeling
- Verify conventions propagation

---

## Migration Path

### For Existing Sessions (Backward Compatibility)
- Sessions without memory continue to work
- Memory is optional enhancement
- Can add memory to existing session manually

### For New Sessions
- Prompt user: "Generate single entity or bounded context?"
- If bounded context: Initialize memory with all table names
- If single entity: No memory needed

---

## Documentation Requirements

### User Documentation
- Tutorial: "Generating a Bounded Context"
- Guide: "Working with Project Memory"
- Reference: Memory file format specification

### Developer Documentation
- ADR: Cross-Entity Memory Architecture
- API Reference: MemoryManager, ProjectMemory
- Integration Guide: Adding memory to custom profiles

---

## Future Enhancements

### Memory Visualization
```bash
aiwf memory graph --session {id}
```
Generates dependency graph showing:
- Completed entities (green)
- In-progress entities (yellow)
- Pending entities (gray)
- Relationships (arrows)

### Memory Analysis
```bash
aiwf memory analyze --session {id}
```
Reports:
- Naming consistency score
- Relationship completeness
- Convention adherence
- Suggested improvements

### Memory Templates
```bash
aiwf memory init --template spring-boot-saas
```
Pre-configured memory for common project types:
- Multi-tenant SaaS
- E-commerce platform
- CMS system

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Memory file corruption | High | Atomic writes, validation on load |
| Memory grows too large | Medium | Pagination, archival of old entities |
| Inconsistent updates | High | Transaction-like updates, rollback on failure |
| Memory diverges from reality | Medium | Validation commands, repair tools |
| Complex memory merging | Low | Single-writer model (no concurrent updates) |

---

## Success Criteria

Feature is complete when:
- ✅ Can initialize memory for multi-table project
- ✅ Memory context injected into generation prompts
- ✅ Memory updated after each successful generation
- ✅ Later entities correctly reference earlier entities
- ✅ Consistent naming across 20+ entities
- ✅ <10% revision rate for consistency issues
- ✅ All unit and integration tests passing
- ✅ Documentation complete

---

## References

- ADR-0001: Architecture Overview (session persistence foundation)
- ADR-0002: Layered Template Composition (memory injection mechanism)

---

**Document Status:** Proposed Enhancement  
**Last Updated:** December 11, 2024  
**Next Review:** After Phase 3 completion
