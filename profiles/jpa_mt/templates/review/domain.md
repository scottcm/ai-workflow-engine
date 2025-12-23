{{include: ../_shared/base.md}}
{{include: ../_shared/fallback-rules.md}}
{{include: ../_phases/review-guidelines.md}}

---

# Domain Layer Review

Reviewing **domain layer** artifacts only:
- Entity class(es)
- Repository interface(s)

**Out of scope:** Services, controllers, DTOs, mappers.

---

## Review Checklist

### Entity Review

- [ ] All planned fields present with correct types
- [ ] Field types match schema DDL
- [ ] Relationships match plan (correct Target Entity imports)
- [ ] Annotations per standards (JPA, validation)
- [ ] No extra fields not in plan
- [ ] Base class inheritance correct (if applicable)

### Repository Review

- [ ] All planned methods present
- [ ] Method signatures match plan
- [ ] Follows standards patterns
- [ ] Tenant scoping correct (if applicable)
- [ ] No extra methods not in plan

### Integration

- [ ] Entity/repository references valid
- [ ] Imports resolve correctly (especially cross-schema)
- [ ] No scope violations (business logic in entities)

---

## Completion

Answer: Are all planned artifacts present, implementing the plan exactly, following standards?

Missing artifacts or plan deviations are CRITICAL.

---

## Output Destination

Save your complete review as `review-response.md` to same location as `review-prompt.md`.