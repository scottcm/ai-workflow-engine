# Getting Started

Quick start guide for using the AI Workflow Engine.

---

## Prerequisites

- Python 3.13+
- Poetry (for development)

---

## Installation

```bash
# Clone repository
git clone https://github.com/scottcm/ai-workflow-engine.git
cd ai-workflow-engine

# Install dependencies
poetry install

# Verify installation
poetry run aiwf --help
```

---

## Your First Workflow

This guide uses the `jpa-mt` profile to generate a JPA entity.

### Step 1: Initialize Session

```bash
poetry run aiwf init jpa-mt \
  -c entity=Product \
  -c table=catalog.products \
  -c bounded-context=catalog \
  -c scope=domain \
  -c schema-file=schema.sql
```

This creates a session and generates the planning prompt.

### Step 2: Check Status

```bash
poetry run aiwf status <session-id>
```

Output shows current phase and stage:
```
phase=PLAN
stage=PROMPT
status=IN_PROGRESS
```

### Step 3: Review Planning Prompt

Open the generated prompt file:
```
.aiwf/sessions/<session-id>/iteration-1/planning-prompt.md
```

Edit if needed, then approve to advance:

```bash
poetry run aiwf approve <session-id>
```

### Step 4: Provide AI Response

For manual mode, the engine creates an empty response file:
```
.aiwf/sessions/<session-id>/iteration-1/planning-response.md
```

Copy the prompt to your AI tool, paste the response into this file, then approve:

```bash
poetry run aiwf approve <session-id>
```

### Step 5: Continue Through Phases

Repeat the prompt → response → approve cycle through:
1. **PLAN** - Create implementation plan
2. **GENERATE** - Generate code
3. **REVIEW** - Review generated code
4. **REVISE** (if needed) - Address review feedback

### Step 6: Collect Output

Generated code is in:
```
.aiwf/sessions/<session-id>/iteration-1/code/
```

---

## Automated Workflows

For fully automated execution, use AI providers:

```bash
# Use Claude Code for all phases
poetry run aiwf init jpa-mt \
  -c entity=Product \
  -c table=catalog.products \
  -c bounded-context=catalog \
  -c scope=domain \
  -c schema-file=schema.sql \
  --planner claude-code \
  --generator claude-code \
  --reviewer claude-code \
  --reviser claude-code
```

Available providers:
- `manual` - User copies prompts/responses (default)
- `claude-code` - Claude Code CLI (SDK-based)
- `gemini-cli` - Google Gemini CLI

Validate provider availability:
```bash
poetry run aiwf validate ai claude-code
```

---

## Session Management

### List Sessions

```bash
# All sessions
poetry run aiwf list

# Filter by status
poetry run aiwf list --status in_progress

# Filter by profile
poetry run aiwf list --profile jpa-mt
```

### Session Directory Structure

```
.aiwf/sessions/<session-id>/
├── session.json              # Workflow state
├── standards-bundle.md       # Standards snapshot
├── plan.md                   # Approved plan
└── iteration-1/
    ├── planning-prompt.md
    ├── planning-response.md
    ├── generation-prompt.md
    ├── generation-response.md
    ├── review-prompt.md
    ├── review-response.md
    └── code/
        ├── Product.java
        └── ProductRepository.java
```

---

## Available Profiles

List available profiles:
```bash
poetry run aiwf profiles
```

Get profile details:
```bash
poetry run aiwf profiles jpa-mt
```

Profile-specific commands:
```bash
# Show jpa-mt scopes
poetry run aiwf jpa-mt scopes

# Show jpa-mt info
poetry run aiwf jpa-mt info
```

---

## Configuration

Create `.aiwf/config.yml` in your project:

```yaml
providers:
  planner: manual
  generator: claude-code
  reviewer: manual
  reviser: claude-code

hash_prompts: false
```

See [Configuration Guide](configuration.md) for details.

---

## Next Steps

- [Core Concepts](../CONCEPTS.md) - Understand the architecture
- [Creating Profiles](creating-profiles.md) - Build custom profiles
- [Creating Providers](creating-providers.md) - Add AI providers
- [Configuration Guide](configuration.md) - Configure the engine
