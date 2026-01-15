# Configuration Guide

Complete guide to configuring the AI Workflow Engine.

---

## Configuration Files

### Locations

| Location | Scope | Precedence |
|----------|-------|------------|
| CLI flags | Command-specific | Highest |
| `.aiwf/config.yml` | Project | High |
| `~/.aiwf/config.yml` | User | Medium |
| Built-in defaults | System | Lowest |

Higher precedence values override lower ones.

### File Discovery

```
# Project config
<project-root>/.aiwf/config.yml

# User config
~/.aiwf/config.yml  (Linux/macOS)
%USERPROFILE%\.aiwf\config.yml  (Windows)
```

---

## Basic Configuration

### Minimal Config

```yaml
# .aiwf/config.yml
providers:
  planner: manual
  generator: manual
  reviewer: manual
  reviser: manual
```

### Automated Workflow

```yaml
# .aiwf/config.yml
providers:
  planner: claude-code
  generator: claude-code
  reviewer: claude-code
  reviser: claude-code
```

### Default Provider

Use `default` to set all providers at once:

```yaml
providers:
  default: claude-code
  reviewer: manual  # Override just this one
```

Expands to:
```yaml
providers:
  planner: claude-code
  generator: claude-code
  reviewer: manual
  reviser: claude-code
```

---

## Provider Configuration

### Available AI Providers

| Key | Description | fs_ability |
|-----|-------------|------------|
| `manual` | User copies prompts/responses | N/A |
| `claude-code` | Claude Code CLI (SDK-based) | `local-write` |
| `gemini-cli` | Google Gemini CLI | `local-write` |

### Provider-Specific Config

```yaml
providers:
  planner: claude-code
  generator: claude-code

provider_config:
  claude-code:
    model: claude-sonnet-4-20250514
    connection_timeout: 10
    response_timeout: 300

  openai:  # For future OpenAI provider
    api_key: ${OPENAI_API_KEY}
    model: gpt-4
```

### Environment Variables

Use `${VAR}` syntax for environment variables:

```yaml
provider_config:
  openai:
    api_key: ${OPENAI_API_KEY}

  custom:
    endpoint: ${CUSTOM_AI_ENDPOINT}
```

---

## Approval Configuration

### Per-Stage Approval

Configure approval providers for specific stages:

```yaml
workflow:
  defaults:
    ai_provider: claude-code
    approval_provider: skip
    approval_max_retries: 3

  plan:
    prompt:
      approval_provider: manual
    response:
      approval_provider: skip

  generate:
    prompt:
      approval_provider: skip
    response:
      approval_provider: linter
      approver_config:
        command: ruff check
```

### Available Approval Providers

| Key | Behavior |
|-----|----------|
| `skip` | Auto-approve (no gate) |
| `manual` | Wait for user `approve` command |
| `claude-code` | Use AI for approval (via adapter) |

### Approval with AI

Any AI provider can be used as an approver:

```yaml
workflow:
  generate:
    response:
      approval_provider: claude-code
      approval_max_retries: 2
```

---

## Workflow Configuration

### Full Example

```yaml
# Project defaults
providers:
  default: claude-code
  reviewer: manual  # Human reviews code

# Provider-specific settings
provider_config:
  claude-code:
    model: claude-sonnet-4-20250514
    response_timeout: 600

# Approval gates
workflow:
  defaults:
    approval_provider: skip

  plan:
    prompt:
      approval_provider: manual  # Review prompts before sending
    response:
      approval_provider: skip

  generate:
    response:
      approval_provider: linter
      approval_max_retries: 2
      approver_config:
        command: ruff check --fix

  review:
    prompt:
      approval_provider: skip
    response:
      approval_provider: manual  # Human approves review results

# Other settings
hash_prompts: false
dev: "scott"
```

### Workflow Phase Structure

```yaml
workflow:
  defaults:           # Applied to all phases/stages
    ai_provider: manual
    approval_provider: skip

  plan:               # PLAN phase
    prompt:           # PLAN[PROMPT] stage
    response:         # PLAN[RESPONSE] stage

  generate:           # GENERATE phase
    prompt:
    response:

  review:             # REVIEW phase
    prompt:
    response:

  revise:             # REVISE phase
    prompt:
    response:
```

---

## Other Settings

### Hash Prompts

Hash prompt files for audit trail:

```yaml
hash_prompts: true  # Default: false
```

### Developer Identifier

Track who ran the workflow:

```yaml
dev: "scott"
```

Or via CLI:
```bash
aiwf init jpa-mt ... --dev scott
```

### Profiles Directory

Custom profiles location:

```yaml
profiles_dir: /path/to/custom/profiles
```

Default: `~/.aiwf/profiles/`

### Standards Provider

Default standards provider for profiles:

```yaml
default_standards_provider: scoped-layer-fs
```

---

## CLI Overrides

CLI flags override all config files:

```bash
# Override providers
aiwf init jpa-mt ... \
  --planner claude-code \
  --generator claude-code

# Override fs_ability
aiwf approve <session> --fs-ability none

# Override hash behavior
aiwf approve <session> --hash-prompts
aiwf approve <session> --no-hash-prompts
```

---

## Validation

Validate provider configuration:

```bash
# Validate specific provider
aiwf validate ai claude-code

# Validate all AI providers
aiwf validate ai

# Validate everything
aiwf validate all
```

---

## Configuration Precedence

For any setting, the first defined value wins (top to bottom):

1. CLI flags (`--planner`, `--generator`, etc.)
2. Project config (`.aiwf/config.yml`)
3. User config (`~/.aiwf/config.yml`)
4. Built-in defaults

### fs_ability Precedence

For filesystem ability specifically:

1. CLI flag (`--fs-ability`)
2. Config file (`fs_ability` in provider config)
3. Provider metadata (`get_metadata()["fs_ability"]`)
4. Engine default (`local-write`)

---

## Best Practices

### Development Setup

```yaml
# .aiwf/config.yml - Development
providers:
  default: manual  # Full control during development

workflow:
  defaults:
    approval_provider: manual  # Review everything
```

### CI/CD Setup

```yaml
# .aiwf/config.yml - Automated
providers:
  default: claude-code

workflow:
  defaults:
    approval_provider: skip  # Trust AI fully

hash_prompts: true  # Audit trail
```

### Hybrid Setup

```yaml
# .aiwf/config.yml - Mixed
providers:
  planner: claude-code    # AI plans
  generator: claude-code  # AI generates
  reviewer: manual        # Human reviews
  reviser: claude-code    # AI revises

workflow:
  plan:
    prompt:
      approval_provider: manual  # Check prompt first
    response:
      approval_provider: skip

  generate:
    response:
      approval_provider: linter  # Auto-lint

  review:
    response:
      approval_provider: manual  # Human decides
```

---

## Troubleshooting

### Config Not Loading

Check file location:
```bash
# Project config
ls .aiwf/config.yml

# User config
ls ~/.aiwf/config.yml
```

### Invalid YAML

Validate YAML syntax:
```bash
python -c "import yaml; yaml.safe_load(open('.aiwf/config.yml'))"
```

### Provider Not Found

```bash
# List available providers
aiwf providers

# Validate provider
aiwf validate ai claude-code
```

### Environment Variable Not Set

```bash
# Check if variable is set
echo $OPENAI_API_KEY

# Set variable
export OPENAI_API_KEY=sk-...
```

---

## Next Steps

- [Getting Started](getting-started.md) - Quick start guide
- [Creating Providers](creating-providers.md) - Add custom providers
- [ARCHITECTURE.md](../ARCHITECTURE.md) - System design
