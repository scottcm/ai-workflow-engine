# AI Workflow Engine - API Contract

**Version:** 1.0.0-draft  
**Status:** Specification (Implementation Pending)  
**Last Updated:** December 5, 2024

---

## Overview

This document defines the CLI interface contract between the AI Workflow Engine and external integrations (such as the VS Code extension). The engine exposes its functionality exclusively through CLI commands with structured output formats.

**Key Principles:**
- Engine is the authoritative source of workflow state
- All state persistence is engine-managed
- Extension is a UI layer that consumes engine output
- Profiles determine workflow capabilities and phases
- Prompts are file-based (not stdin) due to multi-file complexity

---

## Command Reference

### 1. `aiwf new`

Initialize a new workflow session without executing any phases.

**Syntax:**
```bash
aiwf new --profile <profile> [options]
```

**Required Arguments:**
- `--profile <n>` – Profile to use (e.g., `jpa-mt-domain`, `jpa-mt-vertical`)

**Profile-Specific Arguments:**

*For domain profiles (jpa-mt-domain):*
- `--entity <n>` – Entity name in PascalCase (e.g., `Product`, `Customer`)

*For vertical profiles (jpa-mt-vertical):*
- `--feature <n>` – Feature name (e.g., `OrderProcessing`, `UserManagement`)

**Optional Arguments:**
- `--mode <interactive|automated>` – Execution mode (default: `interactive`)
- `--session-dir <path>` – Custom session directory (default: `.aiwf/sessions/<timestamp>`)
- `--config <path>` – Custom configuration file

**Output (JSON):**
```json
{
  "status": "success",
  "session_id": "20241205-143022-a3f8",
  "session_dir": "/path/to/.aiwf/sessions/20241205-143022-a3f8",
  "profile": "jpa-mt-domain",
  "mode": "interactive",
  "entity": "Product",
  "state": "initialized",
  "next_phase": "planning"
}
```

**Error Output (JSON):**
```json
{
  "status": "error",
  "error_code": "PROFILE_NOT_FOUND",
  "message": "Profile 'invalid-profile' not found",
  "available_profiles": ["jpa-mt-domain"]
}
```

**Exit Codes:**
- `0` – Success
- `1` – Invalid arguments
- `2` – Profile not found
- `3` – Configuration error

---

### 2. `aiwf run`

Create a new session and execute the full workflow (or applicable phases based on mode).

**Syntax:**
```bash
aiwf run --profile <profile> [options]
```

**Arguments:**
Same as `aiwf new`, plus:
- `--auto-approve` – Skip plan approval step in interactive mode (use with caution)
- `--provider <n>` – Override default AI provider for this session

**Behavior:**

*Interactive Mode:*
1. Creates session
2. Generates planning prompt
3. **Stops and waits** for user to provide AI response
4. User places response in `responses/planning.md`
5. User runs `aiwf step generate --session <id>` to continue

*Automated Mode:*
1. Creates session
2. Executes full workflow automatically
3. Streams progress to stdout
4. Returns final state

**Output (JSON):**
```json
{
  "status": "success",
  "session_id": "20241205-143045-b7k2",
  "session_dir": "/path/to/.aiwf/sessions/20241205-143045-b7k2",
  "profile": "jpa-mt-domain",
  "mode": "interactive",
  "state": "awaiting_planning_response",
  "prompt_file": "/path/to/.aiwf/sessions/20241205-143045-b7k2/prompts/planning.md",
  "standards_file": "/path/to/.aiwf/sessions/20241205-143045-b7k2/prompts/standards-bundle.md",
  "instructions": "Copy the contents of planning.md and standards-bundle.md to your AI interface, then paste the response into responses/planning.md and run: aiwf step generate --session 20241205-143045-b7k2"
}
```

**Exit Codes:**
- `0` – Success (session created, awaiting next step)
- `1` – Invalid arguments
- `2` – Profile not found
- `3` – Configuration error
- `4` – Workflow execution error (automated mode)

---

### 3. `aiwf step <phase>`

Execute a single workflow phase for an existing session (interactive mode only).

**Syntax:**
```bash
aiwf step <phase> --session <session-id> [options]
```

**Required Arguments:**
- `<phase>` – Phase name: `planning`, `generate`, `review`, `revise`
- `--session <id>` – Session identifier

**Optional Arguments:**
- `--response-file <path>` – Custom path to AI response (default: `responses/<phase>.md`)

**Phases:**

1. **planning** – Generate planning prompt
2. **generate** – Process planning response and generate code prompt
3. **review** – Generate review prompt for generated code
4. **revise** – Process review feedback and generate revision prompt

**Output (JSON):**
```json
{
  "status": "success",
  "session_id": "20241205-143045-b7k2",
  "phase": "generate",
  "state": "awaiting_generation_response",
  "prompt_file": "/path/to/prompts/generate.md",
  "previous_artifacts": [
    "plans/planning-output.md"
  ],
  "instructions": "Copy generate.md to your AI interface with the planning output, paste response into responses/generate.md, then run: aiwf step review --session 20241205-143045-b7k2"
}
```

**Exit Codes:**
- `0` – Success
- `1` – Invalid arguments
- `2` – Session not found
- `3` – Invalid phase for current state
- `4` – Phase execution error

---

### 4. `aiwf resume`

Continue an existing workflow session from its current state.

**Syntax:**
```bash
aiwf resume <session-id> [options]
```

**Required Arguments:**
- `<session-id>` – Session identifier

**Optional Arguments:**
- `--from-phase <phase>` – Restart from specific phase (discards later state)

**Behavior:**
- Loads session state
- Determines next required action
- In interactive mode: tells user what to do next
- In automated mode: continues execution from checkpoint

**Output (JSON):**
```json
{
  "status": "success",
  "session_id": "20241205-143045-b7k2",
  "profile": "jpa-mt-domain",
  "current_state": "awaiting_generation_response",
  "completed_phases": ["planning"],
  "next_action": "Provide AI response in responses/generate.md, then run: aiwf step review --session 20241205-143045-b7k2",
  "session_dir": "/path/to/.aiwf/sessions/20241205-143045-b7k2"
}
```

**Exit Codes:**
- `0` – Success
- `2` – Session not found
- `3` – Session state corrupted

---

### 5. `aiwf list`

List all workflow sessions.

**Syntax:**
```bash
aiwf list [options]
```

**Optional Arguments:**
- `--status <active|completed|failed|all>` – Filter by status (default: `all`)
- `--profile <n>` – Filter by profile
- `--format <json|table>` – Output format (default: `table`)

**Output (JSON):**
```json
{
  "status": "success",
  "sessions": [
    {
      "session_id": "20241205-143045-b7k2",
      "profile": "jpa-mt-domain",
      "entity": "Product",
      "state": "awaiting_generation_response",
      "created_at": "2024-12-05T14:30:45Z",
      "updated_at": "2024-12-05T14:32:10Z",
      "session_dir": "/path/to/.aiwf/sessions/20241205-143045-b7k2"
    }
  ]
}
```

**Exit Codes:**
- `0` – Success

---

### 6. `aiwf status`

Get detailed status for a specific session.

**Syntax:**
```bash
aiwf status <session-id>
```

**Output (JSON):**
```json
{
  "status": "success",
  "session_id": "20241205-143045-b7k2",
  "profile": "jpa-mt-domain",
  "entity": "Product",
  "mode": "interactive",
  "state": "awaiting_generation_response",
  "completed_phases": [
    {
      "phase": "planning",
      "completed_at": "2024-12-05T14:31:20Z",
      "artifacts": ["plans/planning-output.md"]
    }
  ],
  "current_phase": {
    "phase": "generate",
    "started_at": "2024-12-05T14:32:10Z",
    "awaiting": "AI response in responses/generate.md"
  },
  "session_dir": "/path/to/.aiwf/sessions/20241205-143045-b7k2",
  "created_at": "2024-12-05T14:30:45Z",
  "updated_at": "2024-12-05T14:32:10Z"
}
```

**Exit Codes:**
- `0` – Success
- `2` – Session not found

---

### 7. `aiwf profiles`

List available profiles and their capabilities.

**Syntax:**
```bash
aiwf profiles [options]
```

**Optional Arguments:**
- `--profile <n>` – Show details for specific profile
- `--format <json|table>` – Output format (default: `table`)

**Output (JSON):**
```json
{
  "status": "success",
  "profiles": [
    {
      "name": "jpa-mt-domain",
      "description": "Multi-tenant JPA domain layer generation (Entity + Repository)",
      "target_stack": "Java 21, Spring Data JPA, PostgreSQL",
      "scope": "domain",
      "tenancy": "multi-tenant",
      "generates": ["Entity", "Repository"],
      "required_args": ["entity"],
      "phases": ["planning", "generate", "review", "revise"],
      "supports_automated": true
    },
    {
      "name": "jpa-mt-vertical",
      "description": "Multi-tenant full-stack vertical slice generation",
      "target_stack": "Java 21, Spring Boot, PostgreSQL",
      "scope": "vertical",
      "tenancy": "multi-tenant",
      "generates": ["Entity", "Repository", "Service", "Controller", "DTOs"],
      "required_args": ["feature"],
      "phases": ["planning", "generate", "review", "revise"],
      "supports_automated": true
    }
  ]
}
```

**Exit Codes:**
- `0` – Success

---

## Session State Model

Sessions persist state in `<session-dir>/session.json`:

```json
{
  "session_id": "20241205-143045-b7k2",
  "profile": "jpa-mt-domain",
  "entity": "Product",
  "mode": "interactive",
  "state": "awaiting_generation_response",
  "created_at": "2024-12-05T14:30:45Z",
  "updated_at": "2024-12-05T14:32:10Z",
  "phases": {
    "planning": {
      "status": "completed",
      "started_at": "2024-12-05T14:30:45Z",
      "completed_at": "2024-12-05T14:31:20Z",
      "prompt_file": "prompts/planning.md",
      "response_file": "responses/planning.md",
      "artifacts": ["plans/planning-output.md"]
    },
    "generate": {
      "status": "in_progress",
      "started_at": "2024-12-05T14:32:10Z",
      "prompt_file": "prompts/generate.md"
    }
  },
  "config": {
    "provider": "claude",
    "custom_settings": {}
  }
}
```

**State Values:**
- `initialized` – Session created, no phases started
- `awaiting_<phase>_response` – Waiting for AI response in interactive mode
- `processing_<phase>` – Engine processing phase (automated mode)
- `completed` – All phases successfully completed
- `failed` – Workflow encountered unrecoverable error

---

## Session Directory Structure

```
.aiwf/
  sessions/
    <session-id>/
      session.json              # Session state and metadata
      prompts/
        planning.md             # Generated prompts for each phase
        generate.md
        review.md
        revise.md
        standards-bundle.md     # Standards context (profile-generated)
      responses/                # AI responses (interactive mode)
        planning.md
        generate.md
        review.md
        revise.md
      plans/
        planning-output.md      # Extracted planning artifacts
      artifacts/
        Product.java            # Generated code files
        ProductRepository.java
        gen-context.md          # Generation metadata
      logs/
        workflow.log            # Execution logs
```

---

## Error Handling

All commands return JSON with consistent error format:

```json
{
  "status": "error",
  "error_code": "ERROR_TYPE",
  "message": "Human-readable error message",
  "details": {
    "additional": "context"
  },
  "recovery_suggestion": "What the user should do next"
}
```

**Common Error Codes:**
- `PROFILE_NOT_FOUND` – Specified profile doesn't exist
- `SESSION_NOT_FOUND` – Session ID not found
- `INVALID_STATE` – Operation not valid for current session state
- `MISSING_RESPONSE` – Expected AI response file not found
- `VALIDATION_FAILED` – Generated code failed validation
- `CONFIG_ERROR` – Configuration issue

---

## Integration Guidelines for VS Code Extension

### 1. Command Execution
```typescript
const result = await execAiwf(['run', '--profile', 'jpa-mt-domain', '--entity', 'Product']);
const output = JSON.parse(result.stdout);
if (output.status === 'success') {
  // Handle success
} else {
  // Handle error
}
```

### 2. Session Tracking
- Parse `session.json` to display current state
- Watch `session.json` for changes to update UI
- Use `aiwf status <session-id>` for detailed info

### 3. Interactive Workflow
```typescript
// 1. Start workflow
const session = await execAiwf(['run', '--profile', 'jpa-mt-domain', '--entity', 'Product']);

// 2. Open prompt file for user
await openFile(session.prompt_file);

// 3. Monitor for response file creation
watchFile(session.response_path, () => {
  // 4. Continue to next phase
  await execAiwf(['step', 'generate', '--session', session.session_id]);
});
```

### 4. Error Display
- Parse `error_code` for programmatic handling
- Display `message` to user
- Show `recovery_suggestion` as actionable guidance

---

## Versioning and Compatibility

**Contract Version:** 1.0.0-draft

**Compatibility Promise:**
- Breaking changes will increment major version
- New optional arguments are minor version changes
- Bug fixes are patch version changes

**Version Check:**
```bash
aiwf --version
# Output: aiwf 1.0.0 (contract 1.0.0)
```

The extension should verify contract compatibility at startup.

---

## Future Enhancements (Not in v1.0)

- Streaming output for automated mode
- WebSocket connection for real-time updates
- Parallel phase execution
- Session templates and presets
- Multi-entity workflows
- Custom phase definitions

---

## Notes for Implementation

1. **All output must be valid JSON** (except when `--format table` specified)
2. **Filesystem paths should be absolute** in JSON output
3. **Session IDs must be globally unique** (timestamp + random suffix)
4. **Profile validation happens early** (fail fast on invalid profile)
5. **State transitions are atomic** (session.json updates are transactional)

---

## Support and Feedback

- GitHub Issues: https://github.com/scottcm/ai-workflow-engine/issues
- Discussions: https://github.com/scottcm/ai-workflow-engine/discussions
- Extension Issues: https://github.com/scottcm/aiwf-vscode-extension/issues
