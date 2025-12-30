{{include: ../_shared/base.md}}
{{include: ../_shared/fallback-rules.md}}
{{include: ../_phases/revision-guidelines.md}}

---

# Vertical Slice Revision Request

Previous code generation was reviewed and issues identified. Produce corrected versions of any flagged artifacts:
- Entity class(es)
- Repository interface(s)
- Service class(es)
- Controller class(es)
- Request/Response DTOs
- Mapper(s)

Only include files that require changes.

---

## Revision Rules

1. Fix all CRITICAL issues first
2. Fix MINOR issues if identified
3. Preserve working code - only change what's broken
4. Do not introduce new issues
5. Do not add anything not in the approved plan

---

## Pre-Output Validation

Before emitting bundle, verify:
- All CRITICAL issues addressed
- Fixes don't break other requirements
- Code still implements the approved plan
- No extra artifacts, fields, or methods introduced
- Layer responsibilities maintained

If validation fails, emit single-line error message and no file markers.
