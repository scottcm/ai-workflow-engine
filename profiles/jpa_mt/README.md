# JPA-MT Profile (JPA Multi-Tenant)

## Status

This profile is **under construction**. The portions that are considered stable today are:

- **Standards bundling** via `JpaMtStandardsProvider` (scope-aware, order-preserving, deduplicated)
- **Profile configuration model** (`JpaMtConfig`) validation

Anything beyond that (templates, generation outputs, end-to-end scaffolding conventions) may change.

## Configuration

This profile is configured via YAML:
config.yml is expected to be git-ignored and environment-specific.
- `profiles/jpa_mt/config.yml.example` — **checked in**, generic defaults, safe to share

### How to set it up

1. Copy the example config:
   - `cp profiles/jpa_mt/config.yml.example profiles/jpa_mt/config.yml`

2. Set required environment variables (at minimum):
   - `STANDARDS_DIR` — directory containing the standards markdown files referenced by the config

3. Run the profile/config tests:
   - `pytest -q tests/unit/profiles/jpa_mt/`

### What belongs in each file

- **`config.yml.example`**
  - Uses environment variables (e.g., `${STANDARDS_DIR}`) instead of machine-specific absolute paths
  - Documents available scopes/layers and their default standards mapping

- **`config.yml`**
  - Your real environment values (still preferably via env vars)
  - Any local overrides you do not want to commit

### Documentation

For the complete configuration schema and examples, see: **`profiles/jpa_mt/config.md`**.

## Notes

- YAML `null` is not accepted for list values in `layer_standards`. Use `[]` explicitly:
  - ✅ `dto: []`
  - ❌ `dto:` (parses as `null`)

- Standards file paths in `layer_standards` must be **relative** and must not contain traversal (`../`) or absolute paths.
