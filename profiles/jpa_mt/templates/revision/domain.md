{{include: ../_shared/base.md}}
{{include: ../_shared/fallback-rules.md}}
{{include: ../_phases/revision-guidelines.md}}

---

# Domain Layer Revision Request

## Context

Previous code generation was reviewed and issues identified. Produce corrected versions of:
- JPA entity class
- Spring Data repository interface

---

## Required Inputs

- **Previous Code** - Code from last iteration
- **Review Feedback** - Issues identified by reviewer
- **Standards Bundle** - `standards-bundle.md`
- **Planning Document** - Approved `planning-response.md`

---

## Revision Rules

1. Fix all CRITICAL issues first
2. Fix minor issues if identified
3. Preserve working code - only change what's broken
4. Do not introduce new issues

---

## Output Format

Use same bundle format as generation. Only include modified files:

<<<FILE: Product.java>>>
    package com.example.app.domain.product;

    // Corrected implementation
    
<<<FILE: ProductRepository.java>>>
    package com.example.app.domain.product;

    // Corrected implementation

No prose outside file markers.