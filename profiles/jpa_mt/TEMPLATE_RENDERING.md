# Template Rendering Guide

## Overview

The JPA multi-tenant profile uses a **layered template system** with composition and placeholder filling.

## Architecture

```
Template Files (on disk)
  ↓
{{include:}} Resolution (compose layers)
  ↓
{{PLACEHOLDER}} Filling (inject values)
  ↓
Final Prompt (ready for AI)
```

## Usage

### Step 1: Initialize Profile

```python
from profiles.jpa_mt import JpaMtProfile

# Load profile with config
profile = JpaMtProfile(config)
```

### Step 2: Prepare Context

```python
from datetime import datetime

context = {
    "TASK_ID": "JIRA-123",
    "DEV": "Scott McGee",
    "DATE": datetime.now().strftime("%Y-%m-%d"),
    "ENTITY": "Tier",
    "SCOPE": "domain",
    "TABLE": "global.tiers",
    "BOUNDED_CONTEXT": "catalog",
    "SESSION_ID": session_id,
    "PROFILE": "jpa-mt",
    "ITERATION": str(iteration),
    "scope": "domain", # Profile logic uses lowercase key for template selection
}
```

### Step 3: Render Template

```python
# Render planning prompt
prompt = profile.generate_planning_prompt(context)

# Write to file
prompt_path = session_dir / "iteration-1" / "planning-prompt.md"
prompt_path.write_text(prompt)
```

## Template Layers

### Layer 1: Shared (_shared/)
- `base.md` - Metadata, AI persona, file attachments
- `fallback-rules.md` - Deterministic defaults

### Layer 2: Phase-Specific (_phases/)
- `planning-guidelines.md` - Planning phase behavior
- `generation-guidelines.md` - Code generation behavior
- `review-guidelines.md` - Review phase behavior
- `revision-guidelines.md` - Revision phase behavior

### Layer 3: Scope-Specific (planning/, generation/, etc.)
- `domain.md` - Domain-specific requirements
- `vertical.md` - Vertical-specific requirements

## Include Resolution Rules

The profile supports recursive include resolution:

1.  **Relative Paths:** Start with `./` or `../`
    -   Resolved relative to the **current template file's directory**.
    -   Example: `{{include: ../_shared/base.md}}` inside `planning/domain.md` resolves to `templates/_shared/base.md`.

## Phase 3 Integration Points

The Orchestrator uses the profile's `generate_<phase>_prompt` methods during the `step()` execution to produce prompt files automatically.

## Troubleshooting

### "schema_file not in metadata"
The `jpa-mt` profile requires `--schema-file` during initialization to provide the `{{SCHEMA_DDL}}` placeholder.

### "Circular include detected"
Check templates for circular references:
- A includes B, B includes A ❌
- Fix: Restructure includes to be hierarchical

### "Template not found"
Verify template files exist:
- Phase-scope combination must have template
- Example: `planning/domain.md` for planning + domain scope
