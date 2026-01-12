# AI Workflow Engine

**Production workflow engine for AI-assisted code generation**

[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)

> Production workflow engine built for [Skills Harbor](https://skillsharbor.com)'s multi-tenant SaaS platform to orchestrate AI-assisted JPA entity generation. Open-sourced to demonstrate a practical architectural approach to human-AI collaboration in code generation workflows.

**Version:** v2.0.0 - Full workflow with automated AI providers and approval gates

---

## What This Is

A stateful, resumable workflow orchestrator that manages multi-phase AI-assisted code generation:

```
PLAN → GENERATE → REVIEW → REVISE → COMPLETE
```

Each phase has explicit approval gates, deferred hashing for user edits, and complete audit trails. The engine is language-agnostic; domain logic lives in pluggable **profiles**.

**Production context:** Built to generate JPA/Spring Data entities for Skills Harbor's multi-tenant architecture, handling tenant isolation patterns, row-level security (RLS), and Spring Data repository generation.

---

## What This Demonstrates

| Skill/Pattern | Evidence in Codebase |
|---------------|---------------------|
| **State Machine Design** | [TransitionTable](aiwf/application/transitions.py) - Declarative state machine, [ADR-0012](docs/adr/0012-workflow-phases-stages-approval-providers.md) |
| **Strategy Pattern** | [WorkflowProfile](aiwf/domain/profiles/workflow_profile.py), [AIProvider](aiwf/domain/providers/ai_provider.py), [ApprovalProvider](aiwf/domain/providers/approval_provider.py) |
| **Factory Pattern** | [ProfileFactory](aiwf/domain/profiles/profile_factory.py), [AIProviderFactory](aiwf/domain/providers/provider_factory.py) |
| **Repository Pattern** | [SessionStore](aiwf/domain/persistence/session_store.py) - File-based state persistence |
| **Clean Architecture** | Layered design: Interface (CLI) → Application (Orchestration) → Domain (Models, Profiles) → Infrastructure (Providers) |
| **Approval Gates** | [ADR-0015](docs/adr/0015-approval-provider-implementation.md) - Quality gates with AI/manual/skip strategies |
| **Test Coverage** | 854 unit tests, 84% coverage - [Unit](tests/unit/) + [Integration](tests/integration/) |
| **Type Safety** | Full Pydantic models with mypy enforcement |
| **Security** | [PathValidator](aiwf/domain/validation/path_validator.py) - Path traversal prevention, input validation |
| **Extensibility** | Plugin architecture for profiles, AI providers, standards providers |

---

## Key Features

- **Multi-phase workflow**: PLAN → GENERATE → REVIEW → REVISE with approval gates at each stage
- **Deferred hashing**: Captures user edits before locking artifacts
- **Iteration management**: Full audit trail across revisions with session isolation
- **Mode flexibility**: Manual (copy/paste to AI), CLI agents (claude-code, gemini-cli), or API providers
- **Profile extensibility**: Language/framework-agnostic core, domain logic in profiles
- **Complete audit**: Every prompt, response, and artifact preserved as editable files
- **Budget-friendly**: Works with free AI web interfaces or consumer subscriptions
- **Security-conscious**: Path validation, project isolation, no arbitrary code execution

---

## Quick Start

### Prerequisites

- Python 3.13+
- Poetry 1.7+
- An AI interface (ChatGPT web, Claude.ai, Gemini, or CLI agent)

### Installation

```bash
# Clone and install
git clone https://github.com/scottcm/ai-workflow-engine.git
cd ai-workflow-engine
poetry install
poetry shell
```

### Run Your First Workflow

```bash
# Initialize session for JPA entity generation
aiwf init jpa-mt \
  -c entity=Product \
  -c table=app.products \
  -c bounded-context=catalog \
  -c scope=domain \
  -c schema-file=docker/postgres/db/init/01-schema.sql

# Output shows session ID and creates planning-prompt.md
# Session: abc123-def456
# Phase: PLAN[PROMPT]
# Next: Edit .aiwf/sessions/abc123-def456/iteration-1/planning-prompt.md if needed, then run 'aiwf approve abc123-def456'

# Copy prompt to AI, paste response into planning-response.md, then:
aiwf approve abc123-def456

# Continue through GENERATE, REVIEW, REVISE phases...
# Check status anytime:
aiwf status abc123-def456
```

See [Workflow Tutorial](#workflow-tutorial) for detailed walkthrough.

---

## Architecture Highlights

### Phase + Stage Model

Workflow progresses through phases, each with two stages:

```
PLAN[PROMPT] → approve → PLAN[RESPONSE] → approve →
GENERATE[PROMPT] → approve → GENERATE[RESPONSE] → approve →
REVIEW[PROMPT] → approve → REVIEW[RESPONSE] → approve →
COMPLETE or REVISE[PROMPT] → ...
```

**Approval gates** check "is this ready to proceed?" - not code review (that's the REVIEW phase). Gates check:
- **PROMPT stages**: "Is this prompt clear and complete?"
- **RESPONSE stages**: "Did the AI answer what was asked?"

### Component Separation

| Component | Responsibility |
|-----------|---------------|
| **Engine** | Orchestration, state management, file I/O, approval gates |
| **Profiles** | Domain-specific prompts, response parsing, WritePlans (what to write, not how) |
| **AI Providers** | How AI is accessed (manual, CLI, API) |
| **Approval Providers** | Quality gates (skip, manual, AI-powered) |

**Convention-based boundaries**: Profiles return WritePlans instead of doing I/O. Providers may do I/O based on `fs_ability`. Not enforced by sandbox, relies on component contracts.

### Key Design Decisions

1. **File-materialized semantics**: Every output is a file you can edit (transparency + auditability)
2. **Deferred hashing**: Approval gates run BEFORE hashing, capturing user edits
3. **Non-enforcement policy**: Hash mismatches warn but never block (trust-based, not adversarial)
4. **Iteration directories**: Each revision cycle creates new iteration, preserving history
5. **Approval gate timing**: Gates run immediately after content creation, not on `approve` command

See [Architecture Decision Records](docs/adr/) for detailed rationale.

---

## CLI Reference

### Core Commands

```bash
# Initialize workflow session
aiwf init <profile> -c key=value [-c ...] [--project-dir PATH]

# Advance workflow (resolve pending approval)
aiwf approve <session-id>

# Reject with feedback (halts workflow)
aiwf reject <session-id> --feedback "explanation"

# Check session status
aiwf status <session-id>

# List all sessions
aiwf list [--profile PROFILE] [--status STATUS]

# List available profiles
aiwf profiles

# List available AI providers
aiwf providers

# Validate provider configuration
aiwf validate [--provider PROVIDER]
```

### Global Flags

- `--project-dir PATH` - Set project root (default: current directory)
- `--hash-prompts` - Hash prompt files during approval (audit trail)
- `--no-hash-prompts` - Skip prompt hashing (default)

---

## Workflow Tutorial

### Example: Generate Product Entity

**1. Initialize Session**

```bash
aiwf init jpa-mt \
  -c entity=Product \
  -c table=app.products \
  -c bounded-context=catalog \
  -c scope=domain \
  -c schema-file=docker/postgres/db/init/01-schema.sql
```

Output:
```
Session created: d8f3c2a1-4b7e-4829-9c0d-1a5e8f6b3d2c
Phase: PLAN[PROMPT]
Status: IN_PROGRESS, pending approval

Files created:
  .aiwf/sessions/d8f3c2a1.../iteration-1/planning-prompt.md

Next step: Review prompt, then run 'aiwf approve d8f3c2a1...'
```

**2. Review and Approve Prompt**

```bash
# Optional: Edit planning-prompt.md to refine requirements
# Then approve to trigger AI call (or manual response)
aiwf approve d8f3c2a1
```

**3. Provide AI Response** (Manual Mode)

```bash
# Engine creates planning-response.md
# Copy planning-prompt.md to AI web interface
# Paste AI response into planning-response.md
# Approve to process
aiwf approve d8f3c2a1
```

**4. Continue Through Phases**

Workflow advances: GENERATE → REVIEW → COMPLETE or REVISE

**5. Check Status Anytime**

```bash
aiwf status d8f3c2a1
```

Output shows current phase, stage, files, and next action.

---

## Configuration

Configuration cascades: CLI flags > project config > user config > defaults

### Example Configuration

**`.aiwf/config.yml`:**
```yaml
profile: jpa-mt

workflow:
  defaults:
    ai_provider: manual
    approval_provider: manual
    approval_max_retries: 0
    approval_allow_rewrite: false

  plan:
    prompt:
      approval_provider: skip        # Auto-approve planning prompts
    response:
      approval_provider: manual      # Manual approval for plan

  generate:
    prompt:
      approval_provider: manual
    response:
      approval_provider: manual

  review:
    prompt:
      approval_provider: manual
    response:
      approval_provider: manual      # Review the review

  revise:
    prompt:
      approval_provider: manual
    response:
      approval_provider: manual

hash_prompts: false
dev: null
```

### Available Providers

**AI Providers:**
- `manual` - Human-in-the-loop (copy/paste)
- `claude-code` - Automated via Claude Code CLI
- `gemini-cli` - Automated via Gemini CLI

**Approval Providers:**
- `skip` - Auto-approve (no gate)
- `manual` - Pause for user decision
- Any AI provider key - Delegate approval to AI

See [ADR-0016](docs/adr/0016-v2-workflow-config-and-provider-naming.md) for configuration specification.

---

## JPA Multi-Tenant Profile

The `jpa-mt` profile generates JPA entities, repositories, and tests for multi-tenant Spring Boot applications.

### What It Generates

**Domain Scope:**
- JPA entity with tenant isolation
- Spring Data repository interface
- Repository unit tests

**Vertical Scope:**
- All of domain scope, plus:
- REST controller with CRUD endpoints
- Service layer with business logic
- Integration tests

### Required Context

```bash
-c entity=EntityName          # Java class name
-c table=schema.table_name    # Database table
-c bounded-context=name       # Domain context
-c scope=domain|vertical      # Generation scope
-c schema-file=path/to.sql    # DDL for reference
```

### Multi-Tenant Patterns Supported

- Tenant ID columns with automatic filtering
- Row-level security (RLS) integration
- Global vs tenant-scoped tables
- Composite keys with tenant discrimination

### Example Output Structure

```
iteration-1/code/
├── Product.java              # JPA entity
├── ProductRepository.java    # Spring Data repository
└── ProductRepositoryTest.java
```

---

## Extending the Engine

### Adding a New Profile

1. Implement `WorkflowProfile` ABC
2. Define prompt generation methods
3. Implement response processing (return WritePlan)
4. Register in `ProfileFactory`

```python
from aiwf.domain.profiles.workflow_profile import WorkflowProfile

class MyProfile(WorkflowProfile):
    def generate_plan_prompt(self, context: dict) -> str:
        return f"Generate plan for {context['entity']}"

    def process_plan_response(self, content: str, context: dict) -> ProcessingResult:
        # Parse response, return WritePlan
        return ProcessingResult(
            write_plan=WritePlan(operations=[...]),
            success=True
        )
```

See [docs/EXTENDING.md](docs/EXTENDING.md) for detailed guide.

### Adding a New AI Provider

```python
from aiwf.domain.providers.ai_provider import AIProvider
from aiwf.domain.models.ai_provider_result import AIProviderResult

class MyProvider(AIProvider):
    def validate(self) -> None:
        # Check configuration, connectivity
        pass

    def generate(self, prompt: str, context: dict | None = None) -> AIProviderResult:
        # Call AI, return result
        return AIProviderResult(files={"response.md": content})
```

Register in `AIProviderFactory`.

---

## Documentation

### Architecture

- **[ADR Index](docs/adr/)** - All architecture decision records
- **[ADR-0001: Architecture Overview](docs/adr/0001-architecture-overview.md)** - Start here for architecture
- **[ADR-0012: Phase+Stage Model](docs/adr/0012-workflow-phases-stages-approval-providers.md)** - Workflow model details
- **[ADR-0015: Approval Providers](docs/adr/0015-approval-provider-implementation.md)** - Approval gates system
- **[API-CONTRACT.md](API-CONTRACT.md)** - Complete CLI interface specification

### Guides

- **[docs/CONCEPTS.md](docs/CONCEPTS.md)** - Detailed component explanations
- **[docs/EXTENDING.md](docs/EXTENDING.md)** - Extension development guide
- **[CHANGELOG.md](CHANGELOG.md)** - Version history and release notes

---

## Development Setup

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=aiwf --cov-report=html

# Run unit tests only
pytest tests/unit/ -v

# Run specific test
pytest tests/unit/application/test_workflow_orchestrator.py -v

# Run tests matching pattern
pytest -k "approval" -v
```

**Test suite:** 854 unit tests with 84% code coverage

### Code Quality

```bash
# Type checking
mypy aiwf

# Linting
ruff check aiwf

# Auto-fix
ruff check --fix aiwf
```

### Development Database (Optional)

PostgreSQL with multi-tenant schema for testing:

```bash
# Start database
docker-compose -f docker/postgres/docker-compose.yml up -d

# Connection: localhost:5432, DB: aiwf_test, User: aiwf_user, Pass: aiwf_pass

# Stop when done
docker-compose -f docker/postgres/docker-compose.yml down
```

Schema includes tenant-scoped tables with RLS patterns matching jpa-mt profile targets.

---

## Known Limitations

**V2.0 Constraints:**
- Single bundled profile (`jpa-mt`)
- Limited AI provider ecosystem (manual, claude-code, gemini-cli)
- File-based session storage only (no database backend)
- Single workflow per session (no parallel phase execution)

**Design Trade-offs:**
- Convention-based component boundaries (not enforced by sandbox)
- Trust-based audit (hash mismatches warn but don't block)
- Manual iteration increments (no auto-loop on review rejection)

See [GitHub Issues](https://github.com/scottcm/ai-workflow-engine/issues) for roadmap.

---

## Project Status

**Current Version:** 2.0.0 (January 2026)

**Production Use:** Active at Skills Harbor for JPA entity generation

**Maintenance:** Project is maintained and accepting contributions. Issues and PRs welcome.

---

## License

MIT License - see [LICENSE](LICENSE) file for details.

**Attribution:** Built by Scott Mulcahy for Skills Harbor. Open-sourced to share architectural patterns for AI-assisted development workflows.

---

## Author

**Scott Mulcahy**
Email: scott@skillsharbor.com
GitHub: [@scottcm](https://github.com/scottcm)

**Seeking opportunities in:**
- Backend architecture (Python, Java/Spring Boot)
- AI-assisted development tooling
- Multi-tenant SaaS platforms
- Developer experience engineering

This project demonstrates production-grade system design, clean architecture, and thoughtful API design. Available for contract work or full-time roles.