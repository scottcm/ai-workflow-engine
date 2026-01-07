# TODO: Add --project-dir CLI Flag

## Problem

Currently the engine assumes the current working directory is the project root:
- `.aiwf/` directory is created in CWD
- All relative paths in config are relative to CWD
- User must `cd` to project directory before running commands

## Solution

Add `--project-dir` global option to the CLI:

```bash
# Current (must cd first)
cd C:/Users/scott/projects/skillsharbor
aiwf jpa-mt init --entity User ...

# Proposed (run from anywhere)
aiwf --project-dir C:/Users/scott/projects/skillsharbor jpa-mt init --entity User ...
```

## Implementation

### 1. Add CLI Option (cli.py)

```python
@click.group(help="AI Workflow Engine CLI.")
@click.option("--json", "json_output", is_flag=True, help="Emit machine-readable JSON.")
@click.option("--project-dir", type=click.Path(exists=True, file_okay=False),
              help="Project root directory (default: current directory)")
@click.pass_context
def cli(ctx: click.Context, json_output: bool, project_dir: str | None) -> None:
    ctx.ensure_object(dict)
    ctx.obj["json"] = bool(json_output)
    ctx.obj["project_dir"] = Path(project_dir) if project_dir else Path.cwd()
```

### 2. Update Session Paths

Replace all uses of `DEFAULT_SESSIONS_ROOT` with context-derived path:

```python
# Before
session_store = SessionStore(sessions_root=DEFAULT_SESSIONS_ROOT)

# After
project_dir = ctx.obj.get("project_dir", Path.cwd())
sessions_root = project_dir / ".aiwf" / "sessions"
session_store = SessionStore(sessions_root=sessions_root)
```

### 3. Files to Update

| File | Changes |
|------|---------|
| aiwf/interface/cli/cli.py | Add option, pass through context |
| aiwf/domain/constants.py | Make DEFAULT_SESSIONS_ROOT a function |
| Commands: step, approve, reject, status, list, retry | Use project_dir from context |

### 4. Config Loading

When `--project-dir` is specified:
- Load `.aiwf/config.yml` from that directory
- Resolve relative paths in config relative to project_dir

## Alternatives Considered

1. **Environment variable:** `AIWF_PROJECT_DIR=/path aiwf ...`
   - Pro: Simpler implementation
   - Con: Less explicit, harder to script

2. **Config file in home:** `~/.aiwf/config.yml` with `project_dir` setting
   - Pro: Persistent
   - Con: Overcomplicates for single-project use

## Priority

Medium - Nice to have for:
- Global installation scenarios
- CI/CD pipelines
- Multi-project workflows

Not blocking for current development (can `cd` to project).
