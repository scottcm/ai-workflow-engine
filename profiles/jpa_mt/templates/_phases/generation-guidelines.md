## Code Generation Phase Guidelines

Your task is to generate production-quality Java source code based on the approved planning document.

**Input Files:**
1. **planning-response.md** — Approved design from Phase 1
2. **standards-bundle.md** — Coding standards and patterns
3. **Schema DDL** — Database table definition (reference only)

---

### You MUST:

- **Follow the approved plan exactly** — Entity name, fields, relationships per planning doc
- **Apply standards rigorously** — Package structure, annotations, formatting per standards
- **Generate complete, compilable code** — No placeholders, TODOs, or incomplete sections
- **Use proper JPA annotations** — @Entity, @Table, @Column, @ManyToOne, etc.
- **Include all necessary imports** — Fully-qualified or proper import statements
- **Follow Java conventions** — Proper indentation (4 spaces), JavaDoc where appropriate
- **Generate code bundle format** — Use `<<<FILE: filename>>>` separators

---

### You MUST NOT:

- **Deviate from the plan** — Don't add fields, change names, or modify relationships
- **Add unplanned features** — No extra methods, fields, or annotations beyond plan
- **Make assumptions** — If plan is unclear, flag it as error (shouldn't happen at this stage)
- **Generate test files** — Only production code (Entity + Repository)
- **Include build files** — No pom.xml, build.gradle, etc.

---

### Code Quality Standards:

**Entity Requirements:**
- Extends correct base class (per standards)
- Proper @Entity and @Table annotations with schema
- All fields from plan with correct types and annotations
- Relationships mapped per plan with proper fetch strategies
- No redeclaration of base class fields
- Proper equals/hashCode/toString (per standards)

**Repository Requirements:**
- Extends correct base interface (per standards)
- Proper package and naming
- All query methods from plan
- Proper method signatures (parameter names, return types)
- Spring Data method naming conventions OR @Query annotations
- No implementation code (interface only)

---

### Output Format:

Generate a **code bundle** with this exact format:
```
<<<FILE: path/to/Entity.java>>>
    package com.example.domain;
    
    [4-space indented code]

<<<FILE: path/to/EntityRepository.java>>>
    package com.example.domain;
    
    [4-space indented code]
```

**Critical:**
- Each file starts with `<<<FILE: path>>>` (no indentation)
- Code content is **4-space indented** (entire file)
- Blank line between files
- Path must match package structure from plan

---

### Pre-Generation Validation:

Before generating code, verify:

1. ✅ Planning document loaded and understood
2. ✅ Standards bundle loaded and understood
3. ✅ Entity design is clear (name, fields, relationships)
4. ✅ Repository design is clear (base interface, methods)
5. ✅ Package structure determined from standards
6. ✅ All types and annotations known
7. ✅ No ambiguities remaining (plan should be complete)

If validation fails: `VALIDATION FAILED: [issue]. Cannot generate code because: [explanation].`

---