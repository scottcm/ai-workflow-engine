# AI Workflow Engine - Roadmap

## Current Status: MVP Development (Phase 1-3)

**Goal:** Deliver core workflow orchestration with JPA multi-tenant profile

---

## Phase 1: Foundation ✅ COMPLETE
- [x] Architecture design (ADR-0001)
- [x] Domain models (WorkflowState, WorkflowPhase, ExecutionMode)
- [x] Session persistence (SessionStore)
- [x] Profile system (WorkflowProfile interface, ProfileFactory)
- [x] Provider system (AIProvider interface, ProviderFactory)
- [x] Security validation (PathValidator)

---

## Phase 2: Profile Configuration ✅ COMPLETE
- [x] JPA-MT profile configuration (config.yml)
- [x] Layered template system (ADR-0002)
- [x] Template composition (_shared/, _phases/, scope templates)
- [x] Template renderer with include resolution
- [x] Planning template (domain scope)
- [x] Standards bundling and validation

---

## Phase 3: Code Generation (IN PROGRESS)
- [ ] Generation phase template (_phases/generation-guidelines.md)
- [ ] Domain generation template (generation/domain.md)
- [ ] BundleExtractor (infrastructure/parsing)
- [ ] FileWriter (infrastructure/filesystem)
- [ ] Manual generation helper scripts
- [ ] End-to-end generation workflow test

**Target:** December 2024

---

## Phase 4: Review & Revision
- [ ] Review phase template
- [ ] Revision phase template
- [ ] Issue tracking in WorkflowState
- [ ] Iteration management
- [ ] Review validation rules

**Target:** January 2025

---

## Phase 5: Workflow Orchestration
- [ ] Workflow executor (handler chain)
- [ ] Phase transition logic
- [ ] State management between phases
- [ ] Error handling and recovery
- [ ] Interactive mode checkpoints

**Target:** January 2025

---

## Phase 6: CLI Interface
- [ ] `aiwf new` - Initialize session
- [ ] `aiwf run` - Start workflow
- [ ] `aiwf step` - Execute single phase
- [ ] `aiwf resume` - Continue workflow
- [ ] `aiwf status` - Display session status
- [ ] `aiwf list` - List sessions
- [ ] `aiwf profiles` - List available profiles

**Target:** February 2025

---

## Phase 7: VS Code Extension Integration
- [ ] CLI API stabilization
- [ ] Extension integration testing
- [ ] Session management UI
- [ ] File preview and review
- [ ] Extension documentation

**Target:** February-March 2025

---

## Future Enhancements (Post-MVP)

### High Priority

#### Cross-Entity Workflow Memory
**Status:** Proposed  
**Description:** Persistent memory system for multi-table projects  
**Documentation:** [docs/enhancements/cross-entity-memory.md](enhancements/cross-entity-memory.md)  
**Benefit:** Consistent code generation across 20+ related entities  
**Effort:** 1-2 weeks  
**Target:** v2.0

#### Vertical Scope Implementation
**Status:** Designed, Not Implemented  
**Description:** Full-stack generation (Entity → Controller)  
**Templates:** Designed in Phase 2, need implementation  
**Effort:** 2-3 weeks  
**Target:** v2.0

#### Automated Provider Integration
**Status:** Architecture Complete, Not Implemented  
**Description:** Direct CLI agent execution (claude, gemini)  
**Components:** Provider implementations, automated mode  
**Effort:** 1-2 weeks  
**Target:** v2.0

### Medium Priority

#### Additional Profiles
- [ ] Python/SQLAlchemy profile
- [ ] C#/Entity Framework Core profile
- [ ] TypeScript/Prisma profile

#### Batch Operations
- [ ] Generate multiple entities in sequence
- [ ] Dependency-aware ordering
- [ ] Bulk review and approval

#### Standards Management Tools
- [ ] Standards validation
- [ ] Standards versioning
- [ ] Profile-specific standards generator

### Low Priority

#### Advanced Features
- [ ] Multi-bounded-context support
- [ ] Custom workflow phases
- [ ] Plugin system for custom handlers
- [ ] Web UI for workflow management
- [ ] Team collaboration features

---

## Release Planning

### v1.0 - MVP (Q1 2025)
- Core workflow orchestration
- JPA-MT profile (domain scope)
- Interactive mode
- CLI interface
- VS Code extension integration

### v2.0 - Enhanced (Q2 2025)
- Cross-entity memory
- Vertical scope
- Automated providers
- Additional profiles (1-2)
- Batch operations

### v3.0 - Enterprise (Q3 2025)
- Team collaboration
- Advanced customization
- Multiple profiles
- Performance optimizations
- Enterprise documentation

---

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for guidelines on:
- Proposing new features
- Submitting enhancements
- Development workflow
- Testing requirements

---

**Last Updated:** December 11, 2024
