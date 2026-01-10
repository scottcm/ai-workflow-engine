# AI Workflow Engine - API Contract

**Version:** 2.0.0
**Status:** Stable
**Last Updated:** January 2025

---

## Overview

This document defines the CLI interface contract between the AI Workflow Engine and external integrations (such as the VS Code extension). The engine exposes its functionality exclusively through CLI commands with structured output formats.

**Key Principles:**
- Engine is the authoritative source of workflow state
- All state persistence is engine-managed
- Extension is a UI layer that consumes engine output
- Profiles determine workflow capabilities and context requirements
- Prompts are file-based (not stdin) due to multi-file complexity
- Explicit approval gates control workflow progression

---

## Command Summary

| Command | Purpose | Status |
|---------|---------|--------|
| `aiwf init <profile>` | Create new session | Implemented |
| `aiwf approve <session>` | Approve current stage, advance workflow | Implemented |
| `aiwf reject <session>` | Reject current stage with feedback | Implemented |
| `aiwf status <session>` | Get session details | Implemented |
| `aiwf list` | List sessions | Implemented |
| `aiwf validate` | Validate provider configuration | Implemented |
| `aiwf profiles` | List available profiles | Implemented |
| `aiwf providers` | List available AI providers | Implemented |

---

## Global Options

All commands support these global options:

| Option | Description |
|--------|-------------|
| `--json` | Emit machine-readable JSON on stdout |
| `--project-dir <path>` | Project root directory (default: current directory) |

---

## JSON Output Format

All commands support `--json` flag for machine-readable output. Every JSON response includes:

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | int | Always `1` for this contract version |
| `command` | string | The command that was executed |
| `exit_code` | int | Exit code (0=success, non-zero=error) |
| `error` | string | Present only when command fails |

**Error Types:**

- `error`: Command-level exception (invalid arguments, missing files, configuration errors). Present when `exit_code != 0`.
- `last_error`: Workflow state error from a previous operation, preserved in session.json. Present in `status` outputs when the workflow encountered a recoverable error.

**Note:** Fields with `null` values are omitted from JSON output. Consumers should check for field presence rather than null equality.

---

## Commands

### 1. `aiwf init`

Initialize a new workflow session. Context is passed via `-c key=value` pairs.

**Syntax:**
```bash
aiwf init <profile> [options]
```

**Arguments:**
- `<profile>` - Workflow profile to use (e.g., `jpa-mt`)

**Options:**
- `-c, --context <key=value>` - Context pairs (multiple allowed)
- `--planner <provider>` - Provider for planning phase (default: manual)
- `--generator <provider>` - Provider for generation phase (default: manual)
- `--reviewer <provider>` - Provider for review phase (default: manual)
- `--revisor <provider>` - Provider for revision phase (default: manual)
- `--dev <name>` - Developer identifier
- `--task-id <id>` - Task/ticket reference

**Example (jpa-mt profile):**
```bash
aiwf init jpa-mt \
  -c entity=Product \
  -c table=app.products \
  -c bounded-context=catalog \
  -c schema-file=schema.sql
```

**Context Requirements by Profile:**

Use `aiwf <profile> info` to see required context for a specific profile:
```bash
aiwf jpa-mt info
# Shows: entity (required), table (required), bounded_context (required), scope [default: domain], schema_file (required), design
```

**Output (Plain):**
```
session_id=a1b2c3d4e5f6...
phase=plan
stage=prompt
```

**Output (JSON) - Success:**
```json
{
  "schema_version": 1,
  "command": "init",
  "exit_code": 0,
  "session_id": "a1b2c3d4e5f6...",
  "phase": "plan",
  "stage": "prompt"
}
```

**Exit Codes:**
- `0` - Success
- `1` - Error (invalid arguments, missing context, profile not found)

---

### 2. `aiwf approve`

Approve current stage outputs and advance the workflow. Behavior depends on current phase and stage.

**Syntax:**
```bash
aiwf approve <session_id> [options]
```

**Options:**
- `--fs-ability <mode>` - Override provider filesystem capability (`local-write`, `local-read`, `none`)
- `--hash-prompts` - Hash prompt files
- `--no-hash-prompts` - Skip prompt hashing
- `--events` - Emit workflow events to stderr

**Behavior by Phase+Stage:**

| Phase | Stage | Approval Action |
|-------|-------|-----------------|
| PLAN | PROMPT | Call provider, create response file, transition to PLAN[RESPONSE] |
| PLAN | RESPONSE | Hash plan, set plan_approved, transition to GENERATE[PROMPT] |
| GENERATE | PROMPT | Call provider, create response file, transition to GENERATE[RESPONSE] |
| GENERATE | RESPONSE | Hash artifacts, transition to REVIEW[PROMPT] |
| REVIEW | PROMPT | Call provider, create response file, transition to REVIEW[RESPONSE] |
| REVIEW | RESPONSE | Hash review, transition to COMPLETE or REVISE[PROMPT] |
| REVISE | PROMPT | Call provider, create response file, transition to REVISE[RESPONSE] |
| REVISE | RESPONSE | Hash artifacts, transition to REVIEW[PROMPT] |

**Output (JSON) - Success:**
```json
{
  "schema_version": 1,
  "command": "approve",
  "exit_code": 0,
  "session_id": "abc123",
  "phase": "GENERATE",
  "status": "IN_PROGRESS",
  "approved": true,
  "hashes": {
    "plan.md": "a1b2c3d4e5f6..."
  }
}
```

**Exit Codes:**
- `0` - Success
- `1` - Error (missing files, invalid state, provider error)

---

### 3. `aiwf reject`

Reject current content with feedback. Only valid from RESPONSE stages.

**Syntax:**
```bash
aiwf reject <session_id> --feedback <message>
```

**Options:**
- `-f, --feedback <text>` - Feedback explaining rejection (required)

**Output (JSON) - Success:**
```json
{
  "schema_version": 1,
  "command": "reject",
  "exit_code": 0,
  "session_id": "abc123",
  "phase": "PLAN",
  "stage": "response",
  "status": "IN_PROGRESS",
  "feedback": "Plan does not address multi-tenant requirements"
}
```

**Exit Codes:**
- `0` - Success
- `1` - Error (invalid state, not in RESPONSE stage)

---

### 4. `aiwf status`

Get detailed status for a session.

**Syntax:**
```bash
aiwf status <session_id>
```

**Output (Plain):**
```
phase=GENERATE
status=IN_PROGRESS
iteration=1
session_path=.aiwf/sessions/abc123
```

**Output (JSON) - Success:**
```json
{
  "schema_version": 1,
  "command": "status",
  "exit_code": 0,
  "session_id": "abc123",
  "phase": "GENERATE",
  "status": "IN_PROGRESS",
  "iteration": 1,
  "session_path": ".aiwf/sessions/abc123"
}
```

**Exit Codes:**
- `0` - Success
- `1` - Error (session not found)

---

### 5. `aiwf validate`

Validate provider configuration and availability.

**Syntax:**
```bash
aiwf validate <type> [provider_key] [--profile <name>]
```

**Arguments:**
- `<type>` - Provider type: `ai`, `standards`, or `all`
- `[provider_key]` - Optional specific provider to validate

**Options:**
- `--profile <name>` - Profile for standards provider config

**Examples:**
```bash
aiwf validate ai claude-code    # Check if Claude CLI is available
aiwf validate ai                # Validate all AI providers
aiwf validate all               # Validate everything
```

**Output (JSON):**
```json
{
  "schema_version": 1,
  "command": "validate",
  "exit_code": 0,
  "results": [
    {"provider_type": "ai", "provider_key": "manual", "passed": true},
    {"provider_type": "ai", "provider_key": "claude-code", "passed": true}
  ],
  "all_passed": true
}
```

**Exit Codes:**
- `0` - All validations passed
- `1` - One or more validations failed

---

### 6. `aiwf list`

List all workflow sessions.

**Syntax:**
```bash
aiwf list [options]
```

**Options:**
- `--status <status>` - Filter: `in_progress`, `complete`, `error`, `cancelled`, `all` (default: all)
- `--profile <name>` - Filter by profile
- `--limit <n>` - Maximum sessions (default: 50)

**Exit Codes:**
- `0` - Success (even if no sessions found)

---

### 7. `aiwf profiles`

List available workflow profiles or show profile details.

**Syntax:**
```bash
aiwf profiles [profile_name]
```

---

### 8. `aiwf providers`

List available AI providers or show provider details.

**Syntax:**
```bash
aiwf providers [provider_name]
```

---

## Workflow Model

### Phase + Stage Architecture (ADR-0012)

The workflow uses a phase+stage model. Each phase has two stages:
- **PROMPT**: Prompt created, editable, awaiting approval
- **RESPONSE**: AI response received, editable, awaiting approval

### Phases

| Phase | Description |
|-------|-------------|
| INIT | Session created, ready to start |
| PLAN | Creating implementation plan |
| GENERATE | Generating code artifacts |
| REVIEW | Reviewing generated code |
| REVISE | Revising based on review feedback |
| COMPLETE | Workflow finished successfully |
| ERROR | Unrecoverable error |
| CANCELLED | User cancelled |

### Workflow Diagram

```
INIT
  │
  ▼
PLAN[PROMPT] ──approve──► PLAN[RESPONSE] ──approve──►
                                                      │
  ┌───────────────────────────────────────────────────┘
  │
  ▼
GENERATE[PROMPT] ──approve──► GENERATE[RESPONSE] ──approve──►
                                                              │
  ┌───────────────────────────────────────────────────────────┘
  │
  ▼
REVIEW[PROMPT] ──approve──► REVIEW[RESPONSE]
                                   │
                    ┌──────────────┴──────────────┐
                    │                             │
                    ▼ (PASS)                      ▼ (FAIL)
                 COMPLETE                   REVISE[PROMPT]
                                                  │
                                                  ▼
                                           REVISE[RESPONSE]
                                                  │
                                                  └──► REVIEW[PROMPT]
```

### Statuses

| Status | Description |
|--------|-------------|
| `IN_PROGRESS` | Workflow is active |
| `SUCCESS` | Completed successfully |
| `FAILED` | Review failed (triggers revision) |
| `ERROR` | Technical failure |
| `CANCELLED` | User stopped |

---

## Session Directory Structure

```
.aiwf/sessions/<session-id>/
├── session.json                 # Workflow state
├── standards-bundle.md          # Standards snapshot (created at init)
├── plan.md                      # Approved plan (copied after PLAN[RESPONSE] approval)
│
├── iteration-1/
│   ├── planning-prompt.md
│   ├── planning-response.md
│   ├── generation-prompt.md
│   ├── generation-response.md
│   ├── review-prompt.md
│   ├── review-response.md
│   └── code/
│       ├── Entity.java
│       └── EntityRepository.java
│
└── iteration-2/                 # Created if revision needed
    ├── revision-prompt.md
    ├── revision-response.md
    ├── review-prompt.md
    ├── review-response.md
    └── code/
        └── [revised files]
```

---

## Configuration

### Location Precedence (highest wins)

1. CLI flags
2. `./.aiwf/config.yml` (project-specific)
3. `~/.aiwf/config.yml` (user-specific)
4. Built-in defaults

### Structure

```yaml
providers:
  planner: manual
  generator: manual
  reviewer: manual
  revisor: manual

hash_prompts: false
```

---

## Integration Guidelines

### Command Execution

```typescript
async function execAiwf(args: string[]): Promise<AiwfResult> {
  const result = await exec('aiwf', [...args, '--json']);
  return JSON.parse(result.stdout);
}

// Initialize session
const init = await execAiwf([
  'init', 'jpa-mt',
  '-c', 'entity=Product',
  '-c', 'table=app.products',
  '-c', 'bounded-context=catalog',
  '-c', 'schema-file=./schema.sql'
]);

if (init.exit_code === 0) {
  const sessionId = init.session_id;
  // Continue with approve cycle
}
```

### Handling Null Fields

Fields with null values are omitted from JSON output:

```typescript
const iteration = result.iteration ?? 1;
const lastError = result.last_error;  // undefined if not present
```

---

## Versioning

**Contract Version:** 2.0.0

**Compatibility Promise:**
- Breaking changes increment major version
- New optional arguments are minor version changes
- Bug fixes are patch version changes

---

## Support

- GitHub Issues: https://github.com/scottcm/ai-workflow-engine/issues
