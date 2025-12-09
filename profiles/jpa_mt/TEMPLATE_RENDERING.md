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

### Step 1: Create Profile and Renderer

```python
from profiles.jpa_mt import JpaMtProfile, TemplateRenderer

# Load profile with config
profile = JpaMtProfile(config)

# Create renderer
renderer = TemplateRenderer(profile)
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
}
```

### Step 3: Render Template

```python
from aiwf.domain.models.workflow_state import WorkflowPhase

# Render planning prompt
prompt = renderer.render_template(
    phase=WorkflowPhase.INITIALIZED,  # Planning
    scope="domain",
    context=context
)

# Write to file
prompt_path = session_dir / "iteration-1" / "planning-prompt.md"
prompt_path.write_text(prompt)
```

## Template Layers

### Layer 1: Shared (_shared/)
- `base.md` - Metadata, AI persona, file attachments
- `fallback-rules.md` - Deterministic defaults
- `standards-priority.md` - Standards override rule

### Layer 2: Phase-Specific (_phases/)
- `planning-guidelines.md` - Planning phase behavior
- `generation-guidelines.md` - Code generation behavior
- `review-guidelines.md` - Review phase behavior
- `revision-guidelines.md` - Revision phase behavior

### Layer 3: Scope-Specific (planning/, generation/, etc.)
- `domain.md` - Domain-specific requirements
- `vertical.md` - Vertical-specific requirements

## Include Resolution Rules

The renderer supports two types of include paths:

1.  **Relative Paths:** Start with `./` or `../`
    -   Resolved relative to the **current template file's directory**.
    -   Example: `{{include: ../_shared/base.md}}` inside `planning/domain.md` resolves to `templates/_shared/base.md`.

2.  **Root-Relative Paths:** Do not start with `./` or `../`
    -   Resolved relative to the **profile's templates root directory** (`profiles/jpa_mt/templates/`).
    -   Example: `{{include: _shared/base.md}}` resolves to `templates/_shared/base.md` regardless of where it is included from.

## Phase 3 Integration Points

### ManualProvider

```python
class ManualProvider(AIProvider):
    def __init__(self, profile: JpaMtProfile):
        self.renderer = TemplateRenderer(profile)
    
    async def generate(self, prompt: str, context: dict) -> str:
        # Render complete prompt
        rendered = self.renderer.render_template(
            context["phase"],
            context["scope"],
            context
        )
        
        # Write to session directory
        prompt_path = self._get_prompt_path(context)
        prompt_path.write_text(rendered)
        
        # Return placeholder (user will fill manually)
        return f"Prompt written to: {prompt_path}"
```

### Commands

```python
class PreparePlanningCommand(Command):
    def __init__(self, profile: JpaMtProfile):
        self.renderer = TemplateRenderer(profile)
    
    async def execute(self, state: WorkflowState) -> None:
        context = self._build_context(state)
        
        prompt = self.renderer.render_template(
            WorkflowPhase.INITIALIZED,
            state.scope,
            context
        )
        
        # Write prompt file
        self._write_prompt(state, prompt)
```

## Testing

Run tests:
```bash
pytest tests/unit/profiles/jpa_mt/test_template_renderer.py -v
```

## Troubleshooting

### "Missing required context keys"
Ensure all required placeholders are in context dict:
- TASK_ID, DEV, DATE, ENTITY, SCOPE, TABLE, BOUNDED_CONTEXT, SESSION_ID, PROFILE, ITERATION

### "Circular include detected"
Check templates for circular references:
- A includes B, B includes A ❌
- Fix: Restructure includes to be hierarchical

### "Template not found"
Verify template files exist:
- Phase-scope combination must have template
- Example: `planning/domain.md` for planning + domain scope
