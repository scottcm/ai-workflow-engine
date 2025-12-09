# JPA Multi-Tenant Profile

**Profile Name:** `jpa-mt`  
**Version:** 1.0.0  
**Target Stack:** Java 21, Spring Data JPA, PostgreSQL  
**Tenancy Model:** Multi-tenant with row-level security

---

## Overview

The `jpa-mt` profile orchestrates AI-assisted code generation for multi-tenant JPA domain layers and full vertical slices. It supports two scopes:

- **`domain`** - Entity + Repository only
- **`vertical`** - Full stack (Entity → Repository → Service → Controller → DTO → Mapper)

The profile manages standards bundling, prompt generation, code extraction, and artifact organization following a standardized multi-phase AI-assisted workflow pattern.

---

## Configuration File (`config.yml`)

### Complete Example

```yaml
# profiles/jpa-mt/config.yml

standards:
  root: "${STANDARDS_DIR}"

artifacts:
  session_root: ".aiwf/sessions"
  target_root: "${ARTIFACT_ROOT}"
  target_structure: "{entity}/{scope}"
  
  copy_strategy:
    iterations: true
    audit_trail: true
    standards: true

scopes:
  domain:
    description: "Multi-tenant JPA domain layer (Entity + Repository)"
    layers: [entity, repository]
    
  vertical:
    description: "Full vertical slice (Entity → Controller)"
    layers: [entity, repository, service, controller, dto, mapper]

layer_standards:
  _universal:
    - PACKAGES_AND_LAYERS.md
  
  entity:
    - ORG.md
    - JPA_AND_DATABASE.md
    - ARCHITECTURE_AND_MULTITENANCY.md
    - NAMING_AND_API.md
  
  repository:
    - ORG.md
    - JPA_AND_DATABASE.md
    - NAMING_AND_API.md
  
  service:
    - ORG.md
    - BOILERPLATE_AND_DI.md
    - ARCHITECTURE_AND_MULTITENANCY.md
    - NAMING_AND_API.md
  
  controller:
    - ORG.md
    - NAMING_AND_API.md
    - BOILERPLATE_AND_DI.md
  
  dto:
    - ORG.md
    - NAMING_AND_API.md
  
  mapper:
    - ORG.md
    - NAMING_AND_API.md
    - BOILERPLATE_AND_DI.md
```

---

## Configuration Sections

### `standards`

Controls where coding standards files are located.

**Settings:**

- **`root`** (required) - Path to standards directory
  - Can be absolute path, relative path, or environment variable
  - Relative paths are resolved from current working directory
  - Example: `"${STANDARDS_DIR}"` expands from environment
  - Example: `"/path/to/your/project/docs/standards"`
  - Must be an absolute path
  - Directory must exist and be readable

**Purpose:** The engine loads standards files from this location and bundles them for AI consumption. Standards are loaded once per session and remain immutable throughout the workflow to prevent corruption.

**Note on Relative Paths:** When using relative paths, be aware they resolve from the directory where you run the `aiwf` command, not from the profile or config file location.

---

### `artifacts`

Controls where session data and final code are stored.

**Settings:**

- **`session_root`** (required) - Directory for session state and temporary files
  - Default: `".aiwf/sessions"`
  - Relative paths are resolved from current working directory
  - Contains all session data: prompts, responses, extracted code, logs

- **`target_root`** (optional) - Directory for final approved code
  - Can be absolute path, relative path, or environment variable
  - Relative paths are resolved from current working directory
  - If set: Final code copies to `{target_root}/{target_structure}/`
  - If not set: Code remains in session directory only
  - Example: `"${ARTIFACT_ROOT}"` or `"C:/path/to/your/project/docs/standards"`
  - Use when you want final code in your project repository

- **`target_structure`** (required) - Directory pattern within target_root
  - Default: `"{entity}/{scope}"`
  - **Available variables:**
    - `{entity}` - Entity name (e.g., "Tier", "Product")
    - `{scope}` - Scope name (e.g., "domain", "vertical")
    - `{timestamp}` - ISO timestamp of session creation
    - `{session_id}` - Unique session identifier
  - Examples:
    - `"{entity}/{scope}"` → `Tier/domain/`
    - `"{scope}/{entity}"` → `domain/Tier/`
    - `"{entity}"` → `Tier/` (all scopes together)
    - `"generated/{entity}/{scope}/{timestamp}"` → `generated/Tier/domain/2024-12-06T14-30-45/`

- **`copy_strategy`** - Controls what gets copied to target_root
  - **`iterations`** (boolean, default: true)
    - `true`: Copy all iteration folders (full audit trail)
    - `false`: Copy only final iteration
  - **`audit_trail`** (boolean, default: true)
    - `true`: Copy prompts AND responses (both or neither)
    - `false`: Copy neither prompts nor responses
  - **`standards`** (boolean, default: true)
    - `true`: Copy standards-bundle.md to target root
    - `false`: Omit standards from target

**Purpose:** Session directory holds all workflow state and temporary files. Target directory receives final approved code and optional audit trail for version control.

---

### `scopes`

Defines what code generation scopes this profile supports.

**Structure:**

```yaml
scopes:
  {scope_name}:
    description: "Human-readable description"
    layers: [list, of, layers]
```

**Settings:**

- **`{scope_name}`** - Unique identifier (e.g., "domain", "vertical")
- **`description`** - Human-readable explanation of what this scope generates
- **`layers`** - List of architectural layers to generate
  - Must match keys in `layer_standards` section
  - Order matters for template organization
  - Removing a layer excludes its standards and code generation

**Example Scopes:**

```yaml
scopes:
  domain:
    description: "Multi-tenant JPA domain layer (Entity + Repository)"
    layers: [entity, repository]
    
  vertical:
    description: "Full vertical slice (Entity → Controller)"
    layers: [entity, repository, service, controller, dto, mapper]
  
  service-only:
    description: "Service layer only (for extending existing domain)"
    layers: [service]
```

**Purpose:** Scopes let you generate different amounts of code from the same profile. Use `domain` for just persistence layer, `vertical` for complete feature implementation.

**Validation:** Engine warns if a layer appears in `scopes.{name}.layers` but not in `layer_standards`, but allows it (user may be customizing).

---

### `layer_standards`

Maps architectural layers to the standards files that govern them.

**Structure:**

```yaml
layer_standards:
  _universal:              # Applied to ALL scopes
    - STANDARDS_FILE.md
  
  {layer_name}:            # Applied when layer is in scope
    - STANDARDS_FILE.md
    - ANOTHER_STANDARD.md
```

**Settings:**

- **`_universal`** (optional) - Standards applied to every scope
  - Loaded first, before layer-specific standards
  - Example: Package structure, architectural rules
  
- **`{layer_name}`** - Standards for a specific layer
  - Key must match layer names used in `scopes`
  - Filenames are relative to `standards.root`
  - Files are deduplicated automatically (loaded once even if referenced multiple times)

**Standard File Format:**

- Files must exist at `{standards.root}/{filename}`
- Markdown format recommended
- Can include subdirectories: `"java/JPA_STANDARDS.md"`

**Purpose:** The engine collects all standards for the requested scope's layers, deduplicates them, and concatenates them into a single `standards-bundle.md` file with separators.

**Example Bundle Generation:**

For scope `vertical` with layers `[entity, repository, service]`:

```
Loaded files (deduplicated):
- PACKAGES_AND_LAYERS.md (_universal)
- ORG.md (entity, repository, service)
- JPA_AND_DATABASE.md (entity, repository)
- ARCHITECTURE_AND_MULTITENANCY.md (entity, service)
- NAMING_AND_API.md (entity, repository, service)
- BOILERPLATE_AND_DI.md (service)

Result: 6 unique files bundled
```

**Bundle Format:**

```markdown
--- PACKAGES_AND_LAYERS.md ---

[content]

--- ORG.md ---

[content]

--- JPA_AND_DATABASE.md ---

[content]
```

**Standards Immutability:** Once a session starts, standards cannot change. The engine validates that `standards-bundle.md` hasn't been modified between iterations. If standards need updating, create a new session.

---

## Environment Variables

The config file supports environment variable expansion using `${VAR_NAME}` syntax.

**Common Variables:**

```bash
# Set in shell or .env file
export STANDARDS_DIR="/path/to/your/standards"
export ARTIFACT_ROOT="/path/to/your/project/ai-artifacts"
```

**Config Usage:**

```yaml
standards:
  root: "${STANDARDS_DIR}"

artifacts:
  target_root: "${ARTIFACT_ROOT}"
```

**Validation:**

- Undefined variables cause startup error
- Paths are validated for existence and accessibility
- Relative paths in expanded variables are resolved to absolute

---

## Session Directory Structure

When you run a workflow, the engine creates this structure under `{session_root}/{session_id}/`:

```
.aiwf/sessions/{session-id}/
├── session.json                    # State tracking (JSON)
├── workflow.log                    # Execution log
├── standards-bundle.md             # Immutable standards for this session
│
├── iteration-1/
│   ├── planning-prompt.md          # Generated prompt for planning
│   ├── planning-response.md        # AI response (user saves here)
│   ├── generation-prompt.md        # Generated prompt for code generation
│   ├── generation-response.md      # AI code bundle (user saves here)
│   ├── review-prompt.md            # Generated prompt for review
│   ├── review-response.md          # AI review (user saves here)
│   └── code/                       # Extracted code files
│       ├── Tier.java
│       └── TierRepository.java
│
└── iteration-2/                    # Created if revision needed
    ├── revision-planning-prompt.md
    ├── revision-planning-response.md
    ├── revision-generation-prompt.md
    ├── revision-generation-response.md
    ├── review-prompt.md
    ├── review-response.md
    └── code/
        ├── Tier.java
        └── TierRepository.java
```

**File Purposes:**

- **`session.json`** - Tracks workflow state, phase progress, metadata
- **`workflow.log`** - Execution logs for debugging
- **`standards-bundle.md`** - All standards concatenated with separators
- **`*-prompt.md`** - What the engine generates for you to send to AI
- **`*-response.md`** - Where you paste AI's response
- **`code/`** - Extracted from AI's bundled response

---

## Target Directory Structure

If `target_root` is configured, final artifacts copy here on workflow completion:

```
{target_root}/{entity}/{scope}/
├── standards-bundle.md             # If copy_strategy.standards: true
├── Tier.java                       # Final approved code (at root for easy access)
├── TierRepository.java
│
├── iteration-1/                    # If copy_strategy.iterations: true
│   ├── planning-prompt.md          # If copy_strategy.audit_trail: true
│   ├── planning-response.md        # If copy_strategy.audit_trail: true
│   ├── generation-prompt.md
│   ├── generation-response.md
│   ├── review-prompt.md
│   ├── review-response.md
│   └── code/                       # Always copied with iteration
│       ├── Tier.java
│       └── TierRepository.java
│
└── iteration-2/
    └── ...
```

**Access Patterns:**

- **Just want the code?** → Root level: `Tier.java`, `TierRepository.java`
- **Want to see what standards were used?** → Root level: `standards-bundle.md`
- **Need full audit trail?** → `iteration-N/` folders with all prompts and responses
- **Want to recreate what happened?** → Feed prompts back to AI from iteration folders

---

## Workflow Process

### Phase 1: Planning

**Engine generates:**
- `iteration-1/planning-prompt.md` - Request for entity/repository design
- `standards-bundle.md` - All relevant standards

**You do:**
1. Open `planning-prompt.md`
2. Attach `standards-bundle.md` to your AI interface
3. Paste AI's response into `iteration-1/planning-response.md`
4. Run: `aiwf step generate --session {session-id}`

**AI provides:**
- Structured plan for entity design
- Repository query methods
- Multi-tenancy approach
- Implementation notes

---

### Phase 2: Generation

**Engine generates:**
- `iteration-1/generation-prompt.md` - Code generation request
- References: `planning-response.md`, `standards-bundle.md`

**You do:**
1. Attach all three files to AI
2. Paste AI's code bundle into `iteration-1/generation-response.md`
3. Run: `aiwf step review --session {session-id}`

**Engine processes:**
- Parses bundle format (`<<<FILE: filename>>>`)
- Extracts code files to `iteration-1/code/`
- Validates bundle structure

**AI provides:**
```
<<<FILE: Tier.java>>>
    package com.skillsharbor.backend.controlplane.domain.catalog;
    
    [code here, 4-space indented]
    
<<<FILE: TierRepository.java>>>
    package com.skillsharbor.backend.controlplane.domain.catalog;
    
    [code here, 4-space indented]
```

---

### Phase 3: Review

**Engine generates:**
- `iteration-1/review-prompt.md` - Code review request with checklist
- References: `code/*.java`, `standards-bundle.md`

**You do:**
1. Attach review prompt, code files, and standards to AI
2. Paste AI's review into `iteration-1/review-response.md`
3. If PASS: Done! Code copies to target_root (if configured)
4. If FAIL: Run `aiwf step revise --session {session-id}`

**AI provides:**
```
PASS | FAIL

[If FAIL, specific issues with file/line references]
```

---

### Phase 4: Revision (Loop)

**If review fails, engine generates:**
- `iteration-2/revision-planning-prompt.md` - Plan fixes based on review
- References: `iteration-1/review-response.md`, `iteration-1/planning-response.md`

**Process repeats:**
1. Get revision plan from AI
2. Generate revised code (iteration-2)
3. Review revised code
4. If PASS: Done. If FAIL: iteration-3

**Iterations continue until:**
- Review passes
- User manually exits
- Max iterations reached (configurable)

---

## Template Organization

Templates are organized by phase and scope:

```
profiles/jpa-mt/templates/
├── planning/
│   ├── domain.md        # Planning template for domain scope
│   └── vertical.md      # Planning template for vertical scope
├── generation/
│   ├── domain.md
│   └── vertical.md
├── review/
│   ├── domain.md
│   └── vertical.md
└── revision/
    ├── domain.md
    └── vertical.md
```

**Template Selection:**

The profile selects templates based on current phase and requested scope:

```python
# User runs: aiwf run --profile jpa-mt --scope domain --entity Tier
# Engine uses: templates/planning/domain.md
```

**Template Contents:**

- AI role definition
- Task instructions
- Output format requirements
- References to standards and context files
- Behavioral guidelines (when to ask questions, stop, etc.)

---

## Standards File Requirements

Standards files must:

1. **Exist** at `{standards.root}/{filename}`
2. **Be readable** (permissions check)
3. **Use markdown** format (recommended)
4. **Not change** during a session (validated by engine)

**Recommended Structure:**

```markdown
# Standard Name

## Requirements
- MUST/SHOULD/MAY statements

## Examples
[Code examples]

## Anti-patterns
[What not to do]
```

**AI-Optimized Content:**

- Clear, imperative statements
- Concrete examples
- Explicit anti-patterns
- Consistent terminology

---

## Security Considerations

The profile validates all user inputs and file paths:

**Entity Name Validation:**
- Alphanumeric, hyphens, underscores only
- No path traversal characters (`../`)
- No shell metacharacters

**Path Validation:**
- `standards.root` must be absolute path
- `target_root` must be absolute path (if set)
- Paths must exist and be accessible
- Environment variables expanded safely

**Standards File Validation:**
- Files must be within `standards.root` (no path traversal)
- File existence checked before loading
- Read permissions validated

**These protections prevent:**
- Path traversal attacks
- Command injection
- Arbitrary file writes
- Malicious template/standards injection

---

## Customization Examples

### Custom Scope for Service Layer Only

```yaml
scopes:
  service-only:
    description: "Generate service layer for existing domain"
    layers: [service]
```

**Use case:** Domain (Entity/Repository) already exists, need to add service layer.

---

### Minimal Audit Trail

```yaml
artifacts:
  copy_strategy:
    iterations: false      # Only final iteration
    audit_trail: false     # No prompts/responses
    standards: false       # No standards copy
```

**Result:** Only final code files in target directory.

---

### Custom Target Structure

```yaml
artifacts:
  target_structure: "generated/{scope}/{entity}/{timestamp}"
```

**Result:** `generated/domain/Tier/2024-12-06T14-30-45/`

**Use case:** Timestamped generations for comparison.

---

## Validation and Error Handling

**On Profile Load:**

The engine validates:
- Config file syntax (YAML)
- Required sections present
- Path existence and accessibility
- Environment variables defined
- Layer references valid

**Validation Levels:**

1. **ERROR** - Stops execution immediately
   - Missing required sections
   - Invalid file paths
   - Undefined environment variables
   - Invalid YAML syntax

2. **WARNING** - Logs but continues
   - Layer in scope but not in layer_standards
   - Unused layer_standards entries
   - Non-standard target_structure pattern

3. **INFO** - Informational only
   - Environment variable expansion
   - Standards deduplication
   - File existence confirmations

**Common Errors:**

```
ERROR: standards.root path does not exist: /invalid/path
→ Fix: Update STANDARDS_DIR environment variable or use absolute path

ERROR: Layer 'mapper' in scope 'vertical' has no standards defined
→ Fix: Add mapper entry to layer_standards section

WARNING: Layer 'dto' defined in layer_standards but not used in any scope
→ Info: Unused configuration, safe to ignore or remove
```

**Benefits:**

- No manual standards selection
- Consistent artifact organization
- Resumable workflows
- Version control friendly
- Extensible for new scopes

---

## Troubleshooting

### Standards bundle is empty

**Cause:** Layer not mapped in `layer_standards`

**Fix:** Add layer entry:
```yaml
layer_standards:
  your_layer:
    - STANDARD_FILE.md
```

---

### Code not copying to target_root

**Check:**
1. Is `target_root` set in config?
2. Does path exist and have write permissions?
3. Did workflow complete successfully?
4. Check `workflow.log` for copy errors

---

### Template not found

**Cause:** Missing template file for phase/scope combination

**Fix:** Create template at `templates/{phase}/{scope}.md`

Example: `templates/planning/domain.md`

---

### Standards changed during session

**Error:** `StandardsChangedError: Standards have changed since session creation`

**Cause:** `standards-bundle.md` modified or source files changed

**Fix:** Standards are immutable per session. Create new session for updated standards.

---

## Best Practices

1. **Use environment variables** for paths - easier to share configs
2. **Enable full audit trail** in production - helps debug AI issues
3. **Version control target_root** - track AI-generated code evolution
4. **Keep standards focused** - fewer, clearer files better than many overlapping ones
5. **Test templates incrementally** - validate each phase works before full workflow
6. **Document custom scopes** - if you add scopes, explain their purpose

---

## Support

- **GitHub Issues:** https://github.com/scottcm/ai-workflow-engine/issues
- **Discussions:** https://github.com/scottcm/ai-workflow-engine/discussions
- **ADRs:** See `docs/adr/` for architectural decisions
