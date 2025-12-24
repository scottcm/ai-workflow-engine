# AI Workflow Engine - API Contract

**Version:** 0.9.0  
**Status:** Specification  
**Last Updated:** December 24, 2024

---

## Overview

This document defines the CLI interface contract between the AI Workflow Engine and external integrations (such as the VS Code extension). The engine exposes its functionality exclusively through CLI commands with structured output formats.

**Key Principles:**
- Engine is the authoritative source of workflow state
- All state persistence is engine-managed
- Extension is a UI layer that consumes engine output
- Profiles determine workflow capabilities and phases
- Prompts are file-based (not stdin) due to multi-file complexity
- Explicit approval gates control workflow progression

---

## Command Summary

| Command | Purpose | Status |
|---------|---------|--------|
| `aiwf init` | Create new session | Implemented |
| `aiwf step` | Advance workflow one phase | Implemented |
| `aiwf approve` | Hash artifacts, call providers | Implemented |
| `aiwf status` | Get session details | Implemented |
| `aiwf list` | List sessions | Planned |
| `aiwf profiles` | List available profiles | Planned |
| `aiwf providers` | List available AI providers | Planned |

---

## JSON Output Format

All commands support `--json` for machine-readable output. Every JSON response includes:

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | `int` | Output schema version (currently `1`) |
| `command` | `string` | Command name (`"init"`, `"step"`, `"status"`, `"approve"`) |
| `exit_code` | `int` | Exit code (0=success, 1=error, 2=blocked, 3=cancelled) |
| `error` | `string?` | Command-level error message (null on success) |

Additional fields vary by command.

### Error Types

Two error fields may appear in responses:

- **`error`** - Command-level exception (invalid arguments, config errors, file not found)
- **`last_error`** - Workflow state error from previous operation (preserved in session.json)

Both can appear in the same response. `error` indicates the current command failed; `last_error` indicates a prior workflow operation failed.

---

## Implemented Commands

### 1. `aiwf init`

Initialize a new workflow session.

**Syntax:**
```bash
aiwf init --scope <scope> --entity <entity> --table <table> --bounded-context <context> [options]
```

**Required Arguments:**
- `--scope <scope>` - Generation scope (e.g., `domain`, `vertical`)
- `--entity <entity>` - Entity name in PascalCase (e.g., `Product`)
- `--table <table>` - Database table name (e.g., `app.products`)
- `--bounded-context <context>` - Domain context (e.g., `catalog`)

**Optional Arguments:**
- `--schema-file <path>` - Path to DDL schema file (required for jpa-mt profile)
- `--dev <n>` - Developer identifier
- `--task-id <id>` - External task/ticket reference

**Global Options:**
- `--json` - Emit machine-readable JSON output

**Output (Plain):**
```
a1b2c3d4e5f6...
```

**Output (JSON) - Success:**
```json
{
  "schema_version": 1,
  "command": "init",
  "exit_code": 0,
  "error": null,
  "session_id": "a1b2c3d4e5f6..."
}
```

**Output (JSON) - Error:**
```json
{
  "schema_version": 1,
  "command": "init",
  "exit_code": 1,
  "error": "jpa-mt profile requires --schema-file argument"
}
```

**Exit Codes:**
- `0` - Success
- `1` - Error (invalid arguments, configuration error, etc.)

---

### 2. `aiwf step`

Advance the workflow by one phase. The engine determines the next action based on current state.

**Syntax:**
```bash
aiwf step <session_id> [options]
```

**Required Arguments:**
- `<session_id>` - Session identifier from `init`

**Global Options:**
- `--json` - Emit machine-readable JSON output

**Behavior:**

The engine loads current state and performs one unit of work:
- If prompt is missing: generates and writes prompt file
- If response exists: processes response and advances phase
- If awaiting approval: returns current state (no advancement)

**Output (Plain):**
```
phase=PLANNING status=IN_PROGRESS iteration=1 noop_awaiting_artifact=true
.aiwf/sessions/abc123/iteration-1/planning-prompt.md
.aiwf/sessions/abc123/iteration-1/planning-response.md
```

**Output (JSON) - Success:**
```json
{
  "schema_version": 1,
  "command": "step",
  "exit_code": 0,
  "error": null,
  "session_id": "abc123",
  "phase": "PLANNING",
  "status": "IN_PROGRESS",
  "iteration": 1,
  "noop_awaiting_artifact": true,
  "awaiting_paths": [
    ".aiwf/sessions/abc123/iteration-1/planning-prompt.md",
    ".aiwf/sessions/abc123/iteration-1/planning-response.md"
  ],
  "last_error": null
}
```

**Output (JSON) - Blocked:**
```json
{
  "schema_version": 1,
  "command": "step",
  "exit_code": 2,
  "error": null,
  "session_id": "abc123",
  "phase": "PLANNING",
  "status": "IN_PROGRESS",
  "iteration": 1,
  "noop_awaiting_artifact": true,
  "awaiting_paths": [
    ".aiwf/sessions/abc123/iteration-1/planning-prompt.md",
    ".aiwf/sessions/abc123/iteration-1/planning-response.md"
  ],
  "last_error": null
}
```

**Output (JSON) - Error:**
```json
{
  "schema_version": 1,
  "command": "step",
  "exit_code": 1,
  "error": "Session 'abc123' not found",
  "session_id": "abc123",
  "phase": "",
  "status": "",
  "iteration": null,
  "noop_awaiting_artifact": false,
  "awaiting_paths": [],
  "last_error": null
}
```

**Exit Codes:**
- `0` - Success (phase advanced or already complete)
- `1` - Error
- `2` - Blocked awaiting artifact (prompt exists, response missing)
- `3` - Cancelled

---

### 3. `aiwf approve`

Approve current phase outputs, compute hashes, and optionally call AI providers.

**Syntax:**
```bash
aiwf approve <session_id> [options]
```

**Required Arguments:**
- `<session_id>` - Session identifier

**Optional Arguments:**
- `--hash-prompts` - Hash prompt files (overrides config)
- `--no-hash-prompts` - Skip prompt hashing (overrides config)

**Global Options:**
- `--json` - Emit machine-readable JSON output

**Behavior by Phase:**

| Current Phase | Approval Action |
|---------------|-----------------|
| PLANNING | Hash prompt (if enabled), call provider, write response |
| PLANNED | Hash `plan.md`, set `plan_approved=True` |
| GENERATING | Hash prompt (if enabled), call provider, write response |
| GENERATED | Hash all `code/*` files, set artifact `sha256` values |
| REVIEWING | Hash prompt (if enabled), call provider, write response |
| REVIEWED | Hash `review-response.md`, set `review_approved=True` |
| REVISING | Hash prompt (if enabled), call provider, write response |
| REVISED | Hash all `code/*` files, set artifact `sha256` values |

**Output (JSON) - Success:**
```json
{
  "schema_version": 1,
  "command": "approve",
  "exit_code": 0,
  "error": null,
  "session_id": "abc123",
  "phase": "PLANNED",
  "status": "IN_PROGRESS",
  "approved": true,
  "hashes": {
    "plan.md": "sha256:abcdef..."
  }
}
```

**Output (JSON) - Error:**
```json
{
  "schema_version": 1,
  "command": "approve",
  "exit_code": 1,
  "error": "Cannot approve: missing prompt file 'iteration-1/planning-prompt.md'",
  "session_id": "abc123",
  "phase": "PLANNING",
  "status": "ERROR",
  "approved": false,
  "hashes": {}
}
```

**Exit Codes:**
- `0` - Success
- `1` - Error (missing files, invalid state, provider error)

---

### 4. `aiwf status`

Get detailed status for a session.

**Syntax:**
```bash
aiwf status <session_id> [options]
```

**Required Arguments:**
- `<session_id>` - Session identifier

**Global Options:**
- `--json` - Emit machine-readable JSON output

**Output (Plain):**
```
phase=GENERATING
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
  "error": null,
  "session_id": "abc123",
  "phase": "GENERATING",
  "status": "IN_PROGRESS",
  "iteration": 1,
  "session_path": ".aiwf/sessions/abc123",
  "last_error": null
}
```

**Output (JSON) - With Workflow Error:**
```json
{
  "schema_version": 1,
  "command": "status",
  "exit_code": 0,
  "error": null,
  "session_id": "abc123",
  "phase": "GENERATING",
  "status": "IN_PROGRESS",
  "iteration": 1,
  "session_path": ".aiwf/sessions/abc123",
  "last_error": "Failed to process generation response"
}
```

**Output (JSON) - Error:**
```json
{
  "schema_version": 1,
  "command": "status",
  "exit_code": 1,
  "error": "Session 'abc123' not found at .aiwf/sessions/abc123/session.json",
  "session_id": "abc123",
  "phase": "",
  "status": "",
  "iteration": null,
  "session_path": ".aiwf/sessions/abc123"
}
```

**Exit Codes:**
- `0` - Success
- `1` - Error (session not found, corrupted state)

---

## Planned Commands

### 5. `aiwf list`

List all workflow sessions.

**Syntax:**
```bash
aiwf list [options]
```

**Optional Arguments:**
- `--status <status>` - Filter by status (`in_progress`, `complete`, `error`, `all`)
- `--profile <profile>` - Filter by profile

**Global Options:**
- `--json` - Emit machine-readable JSON output

**Output (JSON):**
```json
{
  "schema_version": 1,
  "command": "list",
  "exit_code": 0,
  "error": null,
  "sessions": [
    {
      "session_id": "abc123",
      "profile": "jpa-mt",
      "scope": "domain",
      "entity": "Product",
      "phase": "GENERATING",
      "status": "IN_PROGRESS",
      "iteration": 1,
      "created_at": "2024-12-22T10:30:00Z",
      "updated_at": "2024-12-22T10:35:00Z"
    }
  ]
}
```

**Exit Codes:**
- `0` - Success

---

### 6. `aiwf profiles`

List available workflow profiles.

**Syntax:**
```bash
aiwf profiles [options]
```

**Optional Arguments:**
- `--profile <n>` - Show details for specific profile

**Global Options:**
- `--json` - Emit machine-readable JSON output

**Output (JSON):**
```json
{
  "schema_version": 1,
  "command": "profiles",
  "exit_code": 0,
  "error": null,
  "profiles": [
    {
      "name": "jpa-mt",
      "description": "Multi-tenant JPA domain layer generation",
      "target_stack": "Java 21, Spring Data JPA, PostgreSQL",
      "scopes": ["domain", "vertical"],
      "phases": ["planning", "generation", "review", "revision"]
    }
  ]
}
```

**Exit Codes:**
- `0` - Success

---

### 7. `aiwf providers`

List available AI providers.

**Syntax:**
```bash
aiwf providers [options]
```

**Global Options:**
- `--json` - Emit machine-readable JSON output

**Output (JSON):**
```json
{
  "schema_version": 1,
  "command": "providers",
  "exit_code": 0,
  "error": null,
  "providers": [
    {
      "name": "manual",
      "description": "Human-in-the-loop provider (prompts written to disk)",
      "requires_config": false
    },
    {
      "name": "claude-cli",
      "description": "Anthropic Claude via CLI agent",
      "requires_config": true,
      "config_keys": ["model"]
    }
  ]
}
```

**Exit Codes:**
- `0` - Success

---

## Workflow Model

### Phases

```
INITIALIZED
     |
     v
PLANNING --------> PLANNED
                     |
                     v (requires plan_approved)
                GENERATING --------> GENERATED
                                        |
                                        v (requires artifact hashes)
                                    REVIEWING --------> REVIEWED
                                                           |
              +--------------------------------------------+
              |                                            |
              v (FAIL)                                     v (PASS)
         REVISING --------> REVISED                    COMPLETE
                               |
                               v (requires artifact hashes)
                          REVIEWING
```

### Approval Gates

Every output must be editable before it becomes input to the next step. Approval gates enforce this:

| Phase | Gate | What Gets Approved |
|-------|------|-------------------|
| PLANNED | `plan_approved` | `plan.md` |
| GENERATED | artifact hashes | `iteration-N/code/*` |
| REVIEWED | `review_approved` | `iteration-N/review-response.md` |
| REVISED | artifact hashes | `iteration-N/code/*` |

### Statuses

- `IN_PROGRESS` - Workflow is active
- `SUCCESS` - Workflow completed successfully
- `FAILED` - Review failed (triggers revision)
- `ERROR` - Unrecoverable error
- `CANCELLED` - User cancelled workflow

---

## Session Directory Structure

```
.aiwf/sessions/<session-id>/
├── session.json                 # Workflow state
├── standards-bundle.md          # Immutable standards (created at init)
├── plan.md                      # Approved plan (created in PLANNED)
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

**Key points:**
- `plan.md` at session root (not in subdirectory)
- All prompts and responses flat in iteration directory (no subdirectories)
- Only `code/` subdirectory exists within iterations
- Planning files are in `iteration-1/` (not session root)

---

## Configuration

### Location Precedence (highest wins)

1. CLI flags
2. `./.aiwf/config.yml` (project-specific)
3. `~/.aiwf/config.yml` (user-specific)
4. Built-in defaults

### Structure

```yaml
profile: jpa-mt

providers:
  planner: manual
  generator: manual
  reviewer: manual
  reviser: manual

hash_prompts: false

dev: null
```

---

## Integration Guidelines for VS Code Extension

### Command Execution

```typescript
interface AiwfResult {
  schema_version: number;
  command: string;
  exit_code: number;
  error: string | null;
  [key: string]: unknown;
}

async function execAiwf(args: string[]): Promise<AiwfResult> {
  const result = await exec('aiwf', [...args, '--json']);
  return JSON.parse(result.stdout);
}

// Initialize session
const init = await execAiwf([
  'init',
  '--scope', 'domain',
  '--entity', 'Product',
  '--table', 'app.products',
  '--bounded-context', 'catalog',
  '--schema-file', 'docs/db/01-schema.sql'
]);

if (init.exit_code === 0) {
  const sessionId = init.session_id as string;
  // Continue with step/approve cycle
}
```

### Interactive Workflow Loop

```typescript
async function runWorkflow(sessionId: string) {
  while (true) {
    // Advance workflow
    const step = await execAiwf(['step', sessionId]);
    
    if (step.exit_code === 2) {
      // Awaiting artifact - show user the prompt file
      const paths = step.awaiting_paths as string[];
      await showFile(paths[0]);
      // Wait for user to provide response
      await waitForFile(paths[1]);
      continue;
    }
    
    if (step.phase === 'COMPLETE') {
      break;
    }
    
    // Check if approval needed
    const status = await execAiwf(['status', sessionId]);
    if (needsApproval(status)) {
      // Show artifacts for review
      await showArtifacts(sessionId, status);
      // Wait for user confirmation
      await waitForUserApproval();
      // Approve
      await execAiwf(['approve', sessionId]);
    }
  }
}
```

### Exit Code Handling

```typescript
switch (result.exit_code) {
  case 0:
    // Success - check phase for next action
    break;
  case 1:
    // Error - display error message
    showError(result.error);
    break;
  case 2:
    // Blocked - show awaiting paths to user
    showAwaitingArtifact(result.awaiting_paths as string[]);
    break;
  case 3:
    // Cancelled - workflow terminated
    showCancelled();
    break;
}

// Also check for workflow-level errors
if (result.last_error) {
  showWarning(`Previous workflow error: ${result.last_error}`);
}
```

---

## Versioning

**Contract Version:** 0.9.0

**Compatibility Promise:**
- Breaking changes increment major version
- New optional arguments are minor version changes
- Bug fixes are patch version changes

**Version Check:**
```bash
aiwf --version
# Output: aiwf 0.9.0
```

---

## Support

- GitHub Issues: https://github.com/scottcm/ai-workflow-engine/issues
- Discussions: https://github.com/scottcm/ai-workflow-engine/discussions
- Extension Issues: https://github.com/scottcm/aiwf-vscode-extension/issues