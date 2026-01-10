# Changelog

All notable changes to the AI Workflow Engine project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.0.0] - 2026-01-02

### Summary

Major release introducing automated AI providers and approval gates. The engine now supports fully automated workflows with Claude Code and Gemini CLI, plus configurable approval gates at each workflow stage.

---

### Added

#### AI Response Providers

**Claude Code Provider (ADR-0013)**
- SDK-based integration using `claude-agent-sdk`
- Async wrapper for sync `generate()` interface
- File write tracking via `ToolUseBlock` parsing
- Config validation with granular error handling
- `fs_ability: local-write` for direct file operations

**Gemini CLI Provider (ADR-0014)**
- Subprocess-based integration with NDJSON streaming
- Tracks both `write_file` and `replace` tool calls
- File-based prompt delivery (preferred) with stdin fallback
- Config validation for enum and list types
- Windows compatibility via `shutil.which()` path resolution

#### Approval Provider System (ADR-0015)

**Core Components**
- `ApprovalProvider` ABC with `evaluate()` method
- `SkipApprovalProvider` - Auto-approve (no gate)
- `ManualApprovalProvider` - User's `approve` command IS the decision
- `AIApprovalProvider` - Adapter wrapping any `ResponseProvider`
- `ApprovalProviderFactory` with fallback to wrapped response providers

**Behavioral Contracts**
- Approval gate runs BEFORE artifact hashing
- `retry_count` resets on stage change
- Lenient response parsing with rejection fallback
- `IN_PROGRESS` status on max retries (workflow paused, not failed)
- `suggested_content` passed as hint to provider on retry

**Configuration**
- Per-stage approver configuration
- `max_retries` and `allow_rewrite` options
- Simple and full YAML formats supported

#### State Fields

- `approval_feedback: str | None` - Feedback from last rejection
- `suggested_content: str | None` - Suggested content from approver
- `retry_count: int` - Retry attempts in current stage

---

### Changed

#### Breaking Changes

**Approval Configuration Format**
- New approval config structure required for AI approvers
- Default approver changed from none to `skip`

**Provider Factory Rename**
- `ProviderFactory` renamed to `ResponseProviderFactory`
- Backward compatibility alias maintained

#### Non-Breaking Changes

- Error handling for approval gate failures (keeps workflow `IN_PROGRESS`)
- Context builder pattern for shared keys between providers and approvers

---

### Documentation

- ADR-0013: Claude Code Response Provider (Accepted)
- ADR-0014: Gemini CLI Response Provider (Accepted)
- ADR-0015: Approval Provider Implementation (Accepted)
- Implementation plans converted to specs in `docs/plans/`
- README updated with Approval Providers section

---

### Testing

- 847 unit and integration tests passing
- 12-scenario integration test matrix for approval flows
- Behavioral contract tests for all approval gate behaviors
- Error path tests for provider exceptions and timeouts

---

## [1.0.0] - 2024-12-24

### Summary

First stable release with complete CLI interface. Adds session management commands, profile/provider discovery, and progress messaging for improved developer experience.

---

### Added

#### CLI Commands

**Session Management**
- `aiwf list` - List all workflow sessions with filtering
  - `--status` filter (in_progress, complete, error, cancelled, all)
  - `--profile` filter by profile name
  - `--limit` to cap results (default: 50)
  - Plain text table and JSON output formats

**Discovery Commands**
- `aiwf profiles` - List available workflow profiles
  - Optional `[profile_name]` for detailed view
  - Shows description, target stack, scopes, phases
- `aiwf providers` - List available AI providers
  - Optional `[provider_name]` for detailed view
  - Shows description, config requirements

#### Progress Messaging
- Human-readable progress messages emitted to stderr
- Profile messages: file extraction counts, review verdicts
- Engine messages: phase transitions, approvals, iteration starts
- Truncated file lists for readability (>4 files shows "and N more")
- stdout remains clean for JSON output and scripting

#### Architecture

**Profile/Provider Metadata**
- `WorkflowProfile.get_metadata()` class method for profile discovery
- `AIProvider.get_metadata()` class method for provider discovery
- `ProfileFactory.get_all_metadata()` and `get_metadata(key)` methods
- `ProviderFactory.get_all_metadata()` and `get_metadata(key)` methods

**New Output Models**
- `ListOutput` - Session listing response
- `ProfilesOutput` - Profile listing/detail response
- `ProvidersOutput` - Provider listing/detail response

---

### Changed

- Enhanced error messages throughout workflow orchestrator
- API-CONTRACT.md updated to version 1.0.0

---

### Documentation

- ADR-0005: Chain of Responsibility for Approval Handling (proposed)
- ADR-0006: Observer Pattern for Workflow Events (proposed)
- Updated ADR-0001 to include IntelliJ alongside VS Code
- API-CONTRACT.md: Full specifications for new commands

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

### Under Consideration
- IDE extension integration (VS Code, IntelliJ)
- Additional generation profiles beyond jpa-mt
- OpenAI API response provider
