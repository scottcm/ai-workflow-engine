{{include: ../_shared/base.md}}
{{include: ../_shared/fallback-rules.md}}
{{include: ../_phases/review-guidelines.md}}

---

# Vertical Slice Review

Reviewing **complete vertical slice** artifacts:
- Entity class(es)
- Repository interface(s)
- Service class(es)
- Controller class(es)
- Request/Response DTOs
- Mapper(s)

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

### Service Review

- [ ] All planned methods present
- [ ] Transaction boundaries correct
- [ ] Tenant scoping correct (if applicable)
- [ ] Repository injected correctly
- [ ] No extra methods not in plan

### Controller Review

- [ ] All planned endpoints present
- [ ] HTTP methods correct
- [ ] Request/response types match plan
- [ ] Validation annotations present
- [ ] API path conventions followed
- [ ] No extra endpoints not in plan

### DTO Review

- [ ] All planned DTOs present
- [ ] Fields match plan
- [ ] Validation annotations correct
- [ ] No extra DTOs or fields not in plan

### Mapper Review

- [ ] Mapping approach matches standards
- [ ] All required mappings present
- [ ] Field mappings correct

### Integration

- [ ] All layer references valid
- [ ] Imports resolve correctly (especially cross-schema)
- [ ] No scope violations (wrong layer responsibilities)
- [ ] Dependency injection correct

---

## Completion

Answer: Are all planned artifacts present, implementing the plan exactly, following standards?

Missing artifacts or plan deviations are CRITICAL.
