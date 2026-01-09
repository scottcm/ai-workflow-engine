# Engine Path Architecture - Design Questions

**Status:** Under Discussion
**Date:** 2026-01-06
**Context:** Raised during jpa-mt CR revision work

---

## Active Questions

### Q1: Engine-Managed Variables

What variables should the engine resolve for profiles?

| Variable | Proposed Value | Status |
|----------|----------------|--------|
| `{{PLAN}}` | `.aiwf/sessions/{id}/plan.md` | Exists |
| `{{STANDARDS}}` | `.aiwf/sessions/{id}/standards-bundle.md` | Exists |
| `{{ITERATION_DIR}}` | `.aiwf/sessions/{id}/iteration-{N}` | Proposed |
| `{{CODE_DIR}}` | `.aiwf/sessions/{id}/iteration-{N}/code` | Proposed |
| `{{RESPONSE_FILE}}` | Full output path for AI | Proposed |
| `{{PREV_ITERATION_DIR}}` | Previous iteration (for revision) | Proposed |

**Decision:** TBD - need ADR

### Q2: Working Directories

Should profiles have scratch space?

| Scope | Path | Use Case |
|-------|------|----------|
| Per-iteration | `iteration-{N}/work/` | Temporary files for single iteration |
| Per-session | `sessions/{id}/profile-data/` | Files spanning iterations |

**Decision:** TBD - both seem useful

### Q3: AI Provider CWD

Where should AI providers run from?

| Option | Pros | Cons |
|--------|------|------|
| Workspace root | Access to project files, matches dev mental model | Must construct .aiwf/ paths |
| Session directory | Short paths, isolated | Can't easily access project files |
| .aiwf/ directory | Access to all engine files | Over-broad access, security concern |

**Leaning:** Workspace root with configurable override

### Q4: CWD Configurability

Should CWD be user-configurable?

- Default: workspace root
- Override: via config or CLI flag
- Use case: profiles needing templates outside .aiwf/

**Decision:** Yes, with reasonable default

### Q5: Standards Provider Architecture

Current: Monolithic (repository access + rule processing in one)

Proposed separation:
1. **Repository Adapter**: How to get raw standards (filesystem, git, API)
2. **Rule Processor**: How to transform into bundle format (could be user script)

Engine contract: "Produce a `standards-bundle.md`"

**Decision:** TBD - may need ADR-0017

---

## Impact on Profile Design

### Templates Should NOT Hardcode Paths

**Current (problematic):**
```markdown
Read the plan at `iteration-{{iteration}}/planning-response.md`
```

**Future (better):**
```markdown
Read the approved plan at `{{PLAN}}`
```

### Profiles Should Use Engine Variables

Templates should assume engine will resolve:
- Location of plan, standards, code directory
- Where to write output
- Previous iteration data (for revision)

### Standards Provider Interface

Current interface works but may evolve:
```python
def create_bundle(context, ...) -> str:  # Returns markdown
```

Could become:
```python
def create_bundle(context, ...) -> str:
    raw = self.repository.fetch()  # Adapter
    return self.processor.format(raw)  # Processor
```

---

## Potential Future ADRs

These may be needed but are out of scope for current jpa-mt work:

| ADR | Topic | Why Might Be Needed |
|-----|-------|---------------------|
| 0017 | Data Directory Configuration | User-defined `.aiwf/` location for team/centralized storage |
| 0018 | Provider Configuration | Persistent config for providers (API keys, timeouts, CWD) |
| 0007 update | Plugin Discovery | How to find/load plugin providers from user directories |
| TBD | Engine Variables | Standardize `{{PLAN}}`, `{{CODE_DIR}}`, etc. across profiles |

## Profile-Internal AI Usage

Profiles may want to use AI Providers internally for dynamic prompt generation:

- **Template-only = deterministic** - retry produces identical prompt, no way to incorporate feedback
- **AI-assisted = adaptive** - profile could use registered AI Provider to generate/modify prompts
- **Config approach**: Profile config specifies `ai_provider: "claude-code"` for internal use
- **Benefit**: Profiles don't reinvent AI integration, reuse existing providers

This is a profile design decision, not an engine requirement.

## Next Steps

1. [ ] Continue jpa-mt CR work (current focus)
2. [ ] Note engine gaps as discovered, don't solve them now

---

## References

- Current implementation: `aiwf/application/prompt_assembler.py`
- Profile templates: `profiles/jpa_mt/templates/`
- ADR-0007: Plugin Architecture (related)
