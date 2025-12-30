# ADR-0011: Prompt Builder API

**Status:** Draft
**Date:** December 30, 2024
**Deciders:** Scott

---

## Context and Problem Statement

ADR-0008 established that the engine assembles the final prompt from:
1. Session artifacts (engine-provided)
2. Domain prompt (profile-generated)
3. Output instructions (engine-generated)

Currently, profiles return the domain prompt as a single rendered string. This works but has limitations:

1. **No structure for system prompt separation** - If a provider supports system prompts, the engine cannot easily extract behavioral content (role, constraints) from task content
2. **No validation** - Engine cannot verify profiles provide essential sections
3. **Inconsistent ordering** - Each profile may order sections differently, creating unpredictable prompts

---

## Decision Drivers

1. Enable system/user prompt separation when providers support it
2. Allow engine to validate prompt completeness
3. Maintain profile flexibility for domain-specific needs
4. Keep simple cases simple (profiles that just return a string)

---

## Considered Options

### Option 1: Structured Prompt Builder

Profiles use a builder to populate discrete sections:
- Metadata
- Role
- Context/Inputs
- Task
- Constraints
- Expected Outputs
- Output Format

Engine assembles these sections in consistent order and can route sections to system vs user prompt based on provider capabilities.

**Pros:**
- Enables system prompt separation
- Engine can validate required sections present
- Consistent prompt structure across profiles

**Cons:**
- More API surface for profiles
- May not fit all use cases

---

### Option 2: Pass-Through (Single String)

Profiles return entire domain prompt as one string. Engine only appends output file instructions.

**Pros:**
- Maximum flexibility
- Simple for profiles

**Cons:**
- No system prompt separation possible
- No validation

---

### Option 3: Hybrid (Chosen)

Support both options:
- **Structured builder** for profiles that want engine features (system prompt separation, validation)
- **Pass-through** for profiles that need full control

Engine detects which mode based on return type.

**Pros:**
- Best of both worlds
- Simple cases stay simple
- Advanced features available when needed

**Cons:**
- Two code paths to maintain

---

## Decision Outcome

Adopt **Option 3: Hybrid approach**.

Profiles can either:
1. Return a structured `PromptSections` object with discrete sections
2. Return a raw string (pass-through mode)

### Canonical Prompt Sections

| Section | Owner | Data Type | Description |
|---------|-------|-----------|-------------|
| **Role** | Profile | `str` | Who the AI is acting as |
| **Required Inputs** | Both | `dict[str, str]` | Profile provides `{filename: description}`; engine merges session artifacts |
| **Context** | Profile | `str` | How to use the inputs, domain-specific guidance |
| **Task** | Profile | `str` | What the AI needs to do (**required**) |
| **Constraints** | Profile | `str` | Rules and boundaries |
| **Expected Outputs** | Profile | `list[str]` | Files to produce (under `/code`, supports subdirectories) |
| **Output Format** | Profile | `str` | Content formatting instructions (e.g., "Use Lombok annotations") |

### Engine Responsibilities

Engine adds to the assembled prompt:
- **Metadata** (from workflow state context)
- **Session artifacts** merged into Required Inputs (plan, standards, code files by phase)
- **Output file instructions** (response filename based on fs_ability)
- **Expected output files** rendered from profile's `expected_outputs` list

### Data Structure Details

**Required Inputs** (`dict[str, str]`):
- Profile provides filename → description mapping
- Engine merges its session artifacts (standards-bundle, plan, code) with descriptions
- Rendered as bulleted list in prompt:
  ```markdown
  ## Required Inputs
  - **schema.sql**: Database DDL defining table structure
  - **standards-bundle.md**: Coding standards (engine-provided)
  - **plan.md**: Approved implementation plan (engine-provided)
  ```

**Expected Outputs** (`list[str]`):
- Simple list of file paths, no type metadata
- Supports subdirectories (e.g., `entity/Customer.java`)
- All paths relative to `/code` directory
- Engine uses this list to validate provider results and render output instructions in prompt

**Output Format** (`str`):
- Content formatting instructions only (e.g., "Use Lombok annotations", "Include Javadoc")
- Does NOT include file delimiting - providers write files directly

### Provider Result Model

Providers return a structured result that supports multiple output files:

```python
class ProviderResult(BaseModel):
    """Result from AI provider execution."""
    files: dict[str, str | None]  # {path: content or None if already written}
    response: str | None = None   # Optional commentary for response file
```

**File handling:**
- `files` dict keys are paths relative to `/code` directory
- Value is file content (string) or `None` if provider wrote the file directly
- Engine writes files where content is provided, validates existence where `None`
- Engine warns (does not fail) if expected files are missing

**Provider capability determines behavior:**

| Provider Type | `files` Values | Engine Action |
|---------------|----------------|---------------|
| Local-write capable (Claude Code, Aider) | `None` for all | Validate files exist |
| Non-writing (web chat, API-only) | Content strings | Write files to `/code` |
| Mixed | Some `None`, some content | Write where needed, validate rest |

**Missing file handling:**
- Engine validates all `expected_outputs` exist after provider execution
- Missing files trigger a warning, not an error
- Profile decides acceptability via `process_*_response()` return value
- This allows profile-specific retry or error logic

**Rationale:** This design eliminates response parsing and file extraction. The prompt tells the AI what files to produce; the provider either writes them directly or returns content. No delimiter markers needed.

---

## Consequences

### Positive

- System prompt separation possible for capable providers
- Profiles can opt into validation
- Pass-through preserves flexibility for edge cases
- Clear mental model for what goes where
- No response parsing or file extraction logic needed
- Provider interface supports both file-writing and content-returning providers uniformly
- Eliminates `bundle_extractor` complexity and potential parsing bugs

### Negative

- Two code paths to test (structured vs pass-through)
- Profiles must choose which mode to use
- Provider interface change from `str | None` to `ProviderResult`

---

## Related ADRs

- **ADR-0008**: Engine-Profile Separation of Concerns (defines engine vs profile responsibilities)
- **ADR-0009**: Prompt Structure and AI Provider Capabilities (provider capability metadata)