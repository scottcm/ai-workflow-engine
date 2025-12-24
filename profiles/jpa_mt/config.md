# JPA-MT Profile Configuration (`config.yml`)

This document describes the configuration schema validated by `JpaMtConfig` and consumed by `JpaMtStandardsProvider`.

## File layout and workflow

- `profiles/jpa_mt/config.yml.example` (committed): generic, portable defaults
- `profiles/jpa_mt/config.yml` (local, git-ignored): your environment-specific configuration

Recommended workflow:

1. Copy the example:

   - `cp profiles/jpa_mt/config.yml.example profiles/jpa_mt/config.yml`

2. Customize `profiles/jpa_mt/config.yml` for your environment.

   You may specify paths directly in `config.yml`, or (recommended) use environment variables for portability.

3. Validate:

   - `pytest -q tests/unit/profiles/jpa_mt/`

### Environment variables and `.env` files

Environment variables are **optional**. They are only required if you reference them (e.g., `${STANDARDS_DIR}`).

If you want to use a `.env` file, load it *before* running `aiwf` (for example, via your shell, IDE run configuration, or a dotenv-capable launcher). The profile/config model reads from the process environment; it does not parse `.env` files itself.

## Top-level keys

### `standards`

Configures where standards markdown files are read from.

`standards.root` may be either:

- A literal filesystem path (absolute or relative), or
- A path containing `${ENV_VAR}` placeholders (expanded during validation)

Examples:

```yaml
standards:
  root: "/absolute/path/to/standards"
```

```yaml
standards:
  root: "${STANDARDS_DIR}"
```

Rules:

- Supports `${ENV_VAR}` expansion.
- Validation fails if referenced env vars are undefined.
- Provider reads standards from: `<root>/<relative-path-from-layer_standards>`.

### `scopes`

Defines named bundles of layers. The provider uses `context["scope"]` to select a scope.

Example:

```yaml
scopes:
  domain:
    description: "Multi-tenant JPA domain layer (Entity + Repository)"
    layers: [entity, repository]
```

Rules:

- `scopes` must not be empty.
- Each scope must define `layers` and it must not be empty.

### `layer_standards`

Maps each layer name to a list of standards markdown files (relative to `standards.root`).

Example:

```yaml
layer_standards:
  _universal:
    - ORG.md
    - NAMING_AND_API.md

  entity:
    - db/java/JPA_AND_DATABASE.md

  dto: []
```

Rules:

- `layer_standards` must not be empty.
- Every value must be a list (not `null`, not a string).
- Use `[]` for an intentionally empty list:
  - ✅ `dto: []`
  - ❌ `dto:` (parses as YAML null)
- Paths must be safe relative paths (no absolute paths, no traversal like `../`).

## Standards bundling semantics

When `create_bundle({"scope": "<name>"})` is called:

1. The provider resolves the scope name.
   - Missing or unknown scope raises `ValueError`.

2. Standards file order is determined as:
   - `_universal` first (in configured order), then
   - each layer in `scopes[scope].layers` order, with each layer’s configured order

3. Deduplication is **first occurrence wins**.
   - If a file appears in `_universal` and again in a layer, it is included once (from its first position).

4. Bundle format:
   - Each section begins with a header:
     - `--- <relative-path> ---`
   - Followed by the file contents (normalized to end with a newline).

## Practical guidance

- Prefer keeping `config.yml` portable by using env vars rather than absolute paths, but direct paths are supported.
- If you add new layers to a scope, ensure `layer_standards` defines the layer **or** `_universal` exists (the model enforces coverage rules).
- If you organize standards in subdirectories, list them as relative paths (e.g., `java/ORG.md`) and ensure those subdirectories exist under `standards.root`.
