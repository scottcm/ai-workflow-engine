# Project Description: Cross-Entity Workflow Memory

**Name:** Cross-Entity Workflow Memory System  
**Type:** Core Feature Enhancement  
**Status:** Proposed (Post-MVP)

---

## Overview

A persistent memory system that maintains project-level context across multiple AI workflow sessions, enabling consistent and relationship-aware code generation for multi-table database projects.

---

## Use Case

**Scenario:** Generate vertical stacks (Entity → Repository → Service → Controller) for 23 related database tables in a bounded context.

**Current limitation:** Each table is generated in isolation with no awareness of other tables.

**With memory:** Each generation knows what exists, follows established patterns, and correctly models relationships.

---

## Core Capabilities

1. **Project-wide context tracking** - Maintains list of all entities, their status, and relationships
2. **Convention propagation** - First entity establishes patterns, subsequent entities follow automatically
3. **Relationship awareness** - Entities reference each other correctly with proper types
4. **Progressive building** - Generate entities incrementally with full context
5. **Resumable workflows** - Continue multi-table projects after interruption

---

## Technical Approach

- **Memory storage:** JSON file in session directory
- **Memory structure:** Entities, conventions, relationships, status
- **Integration:** Memory injected into prompts via template includes
- **Updates:** Memory updated after each successful generation
- **Format:** Compact JSON for token efficiency

---

## Success Criteria

- ✅ Generate 20+ related entities with consistent naming
- ✅ Correct relationship modeling across entities
- ✅ <10% revision rate for consistency issues
- ✅ Resume interrupted multi-table projects
- ✅ No manual pattern enforcement needed

---

## Development Phases

**Phase 1:** Core memory system (1 week)  
**Phase 2:** Template integration (1 week)  
**Phase 3:** Enhancements and tooling (future)

---

## Repository Integration

**Suggested structure:**
```
docs/
├── enhancements/
│   └── cross-entity-memory.md         # Full specification
├── roadmap.md                         # Add to future features
└── adr/
    └── XXXX-cross-entity-memory.md    # ADR when implementing
