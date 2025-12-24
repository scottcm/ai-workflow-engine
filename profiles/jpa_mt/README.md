# JPA-MT Profile (JPA Multi-Tenant)

## Status

This profile is **functional**. It supports the complete workflow cycle:
planning → generation → review → revision (with iteration loops).

### Stable Components

- **Standards bundling** via `JpaMtStandardsProvider` (scope-aware, order-preserving, deduplicated)
- **Profile configuration model** (`JpaMtConfig`) with Pydantic validation
- **Template layering system** (`_shared/`, `_phases/`, scope-specific templates)
- **Code extraction** via `bundle_extractor.py` (parses `<<<FILE: >>>` markers)
- **Review metadata parsing** (`review_metadata.py`) - verdict drives workflow progression
- **All four workflow phases**: planning, generation, review, revision

### In Progress

- CLI output messaging improvements

---

## Configuration

This profile is configured via YAML. `config.yml` is expected to be git-ignored and environment-specific.

- `profiles/jpa_mt/config.yml.example` — **checked in**, generic defaults, safe to share

### Setup

1. Copy the example config:
   ```bash
   cp profiles/jpa_mt/config.yml.example profiles/jpa_mt/config.yml
   ```

2. Set required environment variables (at minimum):
   - `STANDARDS_DIR` — directory containing the standards markdown files referenced by the config

3. Run the profile/config tests:
   ```bash
   pytest -q tests/unit/profiles/jpa_mt/
   ```

### What belongs in each file

| File | Purpose |
|------|---------|
| `config.yml.example` | Uses environment variables (e.g., `${STANDARDS_DIR}`). Documents available scopes/layers and their default standards mapping. Safe to commit. |
| `config.yml` | Your real environment values (still preferably via env vars). Any local overrides you do not want to commit. Git-ignored. |

### Documentation

For the complete configuration schema and examples, see: **`profiles/jpa_mt/config.md`**

---

## Usage

Initialize a workflow session with the jpa-mt profile:

```bash
aiwf init \
  --scope domain \
  --entity Product \
  --table app.products \
  --bounded-context catalog \
  --schema-file docs/db/01-schema.sql
```

The `--schema-file` argument is **required** for this profile. It provides the DDL schema used in prompts via the `{{SCHEMA_DDL}}` placeholder.

---

## Notes

- YAML `null` is not accepted for list values in `layer_standards`. Use `[]` explicitly:
  - ✅ `dto: []`
  - ❌ `dto:` (parses as `null`)

- Standards file paths in `layer_standards` must be **relative** and must not contain traversal (`../`) or absolute paths.

- Review responses must include a `@@@REVIEW_META` block with `verdict: PASS` or `verdict: FAIL` to drive workflow progression.