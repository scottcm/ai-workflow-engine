# Changelog

All notable changes to the AI Workflow Engine project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.9.0] - 2024-12-24

### Summary

Initial release of the AI Workflow Engine, a production-ready orchestrator for AI-assisted code generation workflows. Built to demonstrate enterprise architecture patterns while solving real-world multi-tenant SaaS development challenges.

This release includes complete core workflow functionality with a CLI interface. Extended CLI commands (`list`, `profiles`, `providers`) are planned for 1.0.0.

---

### Added

#### Core Engine

**Workflow Orchestration**
- Multi-phase workflow: Planning → Generation → Review → Revision
- Stateful, resumable workflow sessions with persistent state
- Approval system with deferred hashing for artifact validation
- Iteration tracking with incremental revision support
- Explicit phase gates and transition rules
- Non-enforcement policy (hash warnings without blocking workflow)

**Standards & Configuration**
- Standards bundling system with scope-aware selection
- Immutable standards per session (prevents mid-workflow corruption)
- YAML-based configuration with precedence rules (CLI > project > user > defaults)
- Environment variable expansion for flexible deployment

**Artifact Management**
- File-materialized workflow semantics (every output is a file)
- Artifact metadata tracking with SHA-256 hashing
- Iteration-scoped directory structure
- Code extraction from AI responses using `<<<FILE:>>>` markers

**Architecture & Extensibility**
- Profile-based system for language/framework-specific generation
- Strategy pattern for AI providers and workflow profiles
- Factory pattern for runtime instantiation
- Clear responsibility boundaries (profiles generate, engine orchestrates)
- Comprehensive path validation utilities for security

---

#### CLI Interface

**Implemented Commands**
- `aiwf init` - Initialize new workflow sessions
  - Supports scope, entity, table, bounded-context configuration
  - Optional developer and task-id metadata
  - Creates session directory and standards bundle
  
- `aiwf step` - Advance workflow by one deterministic step
  - Generates prompts on phase entry
  - Processes responses when available
  - Reports blocking conditions (awaiting artifacts)
  
- `aiwf approve` - Approve phase outputs
  - Hashes artifacts (deferred to capture user edits)
  - Sets approval flags (plan_approved, review_approved)
  - Optionally hashes prompts (configurable)
  - Calls AI providers in manual mode (writes prompt files)

- `aiwf status` - Query session state
  - Shows current phase, status, iteration
  - Displays session directory path
  - Reports last error if present

**Output Formats**
- Plain text mode for human-readable output
- JSON mode (`--json`) for programmatic consumption
- Consistent exit codes (0=success, 1=error, 2=blocked, 3=cancelled)
- Structured error reporting

---

#### JPA Multi-Tenant Profile (`jpa-mt`)

**Generation Capabilities**
- **Domain scope**: JPA Entity + Spring Data Repository
- **Vertical scope**: Full stack (Entity → Repository → Service → Controller + DTOs)
- Template-based prompt generation with variable substitution
- Schema file integration (DDL provided via `--schema-file`)

**Template System**
- Layered composition with `{{include:}}` directives
- Three-tier structure:
  - Layer 1: Shared (base, fallback rules)
  - Layer 2: Phase-specific (planning, generation, review, revision)
  - Layer 3: Scope-specific (domain, vertical)
- Placeholder filling with context variables
- Circular include detection

**Standards Management**
- Scope-aware standards selection
- Layer-based standards organization
- Deduplication with ordering preservation
- `_universal` fallback for cross-cutting concerns

**Code Processing**
- Extraction via `<<<FILE: filename>>>` markers
- Validation (Java files only, no path traversal)
- Duplicate detection
- WritePlan abstraction for file creation

**Review System**
- Structured metadata parsing (`@@@REVIEW_META` blocks)
- Pass/fail verdict with issue counts
- Display-only semantics (no automated actions based on metadata)
- Graceful degradation (malformed metadata doesn't block workflow)

---

#### State Management & Persistence

**Pydantic-Based Validation**
- Strong typing for all domain models
- Field-level validation with clear error messages
- JSON serialization for persistent state
- Enum-based phase and status tracking

**Core Models**
- `WorkflowState` - Complete session state
- `Artifact` - Code artifact metadata (no content storage)
- `ProcessingResult` - Profile response processing results
- `WritePlan` / `WriteOp` - File write specifications
- `PhaseTransition` - Phase history tracking

**Session Store**
- Atomic writes (temp file + rename)
- JSON-based persistence
- Session directory isolation
- Crash recovery support

---

#### Security & Validation

**Path Validation**
- Entity name sanitization (alphanumeric + underscore/hyphen only)
- Path traversal prevention
- Environment variable expansion with validation
- Absolute/relative path resolution
- Within-root validation for file operations

**Filesystem Boundaries**
- Explicit session roots (`.aiwf/sessions/`)
- Standards directory validation
- Profile-specific template isolation
- Code output directory restrictions

---

#### Testing & Quality

**Test Coverage**
- Comprehensive unit test suite (100% passing)
- Integration tests for workflow orchestration
- Profile-specific test suites
- CLI command testing with JSON output validation
- Approval system test coverage

**Test Utilities**
- Shared fixtures for common test scenarios
- Session directory helpers
- Mock provider implementations
- State assertion utilities

---

#### Documentation

**Architecture Decision Records**
- ADR-0001: Architecture Overview (patterns, responsibility boundaries)
- ADR-0002: Layered Template Composition System
- ADR-0003: Workflow State Validation with Pydantic
- ADR-0004: Structured Review Metadata

**Specifications**
- API-CONTRACT.md: Complete CLI interface specification
- m7_plan.md: Workflow semantics and implementation details
- TEMPLATE_RENDERING.md: Profile template system guide

**Development Artifacts**
- Sample standards documents
- Docker Compose for PostgreSQL test database
- Example configuration files
- Schema and seed data for testing

---

### Technical Debt / Known Limitations

**Planned for 1.0.0**
- `aiwf list` command (list all sessions with filtering)
- `aiwf profiles` command (list available profiles)
- `aiwf providers` command (list available AI providers)

**Future Enhancements (Post-1.0)**
- Automated AI provider integrations (Claude CLI, Gemini CLI)
- Additional profiles beyond jpa-mt
- Plugin discovery and registration
- Enhanced validation and linting
- Performance optimizations

**Intentional Limitations**
- Manual provider only (human-in-the-loop by design)
- Single profile in initial release (extension point exists)
- No multi-user coordination (single developer workflow)
- No AI code sandboxing (out of scope)

---

### Architecture Patterns Demonstrated

**Implemented:**
- **Strategy Pattern** (3 uses): AI providers, workflow profiles, standards providers
- **Factory Pattern**: Runtime instantiation with registration system
- **Repository Pattern**: Session state persistence abstraction
- **State Pattern**: Procedural implementation via phase enum with handlers
- **DTO Pattern**: Pydantic models for type-safe data transfer
- **Dependency Injection**: Constructor-based for testability

---

### Dependencies

**Core**
- Python 3.13
- Pydantic 2.12.5+ (state validation)
- Click 8.3.1+ (CLI framework)
- PyYAML 6.0.3+ (configuration)

**Development**
- pytest 9.0.1+ (testing)
- mypy 1.19.0+ (type checking)
- ruff 0.14.8+ (linting)
- pytest-cov 7.0.0+ (coverage)

---

### Breaking Changes

None (initial release)

---

### Migration Guide

Not applicable (initial release)

---

### Contributors

- Scott Mulcahy (@scottcm) - Architecture, implementation, documentation

---

### License

MIT License - See LICENSE file for details

---

## [Unreleased]

### Planned for 1.0.0
- `aiwf list` - Session listing with filtering
- `aiwf profiles` - Profile discovery
- `aiwf providers` - Provider listing
- Enhanced error messages
- Additional CLI polish

### Under Consideration
- VS Code extension integration
- Automated AI provider support
- Additional generation profiles
- Advanced validation features
