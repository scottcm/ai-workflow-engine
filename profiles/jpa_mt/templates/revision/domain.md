{{include: ../_shared/base.md}}
{{include: ../_shared/fallback-rules.md}}
{{include: ../_phases/revision-guidelines.md}}

---

# Domain Layer Revision Request

## Context

You are in the **Revision** phase for the JPA multi-tenant profile.

- The previous code generation has been reviewed and issues were identified.
- You must correct the identified issues and regenerate the code.

Your task is to produce corrected versions of:

- The **JPA entity class**, and
- The **Spring Data repository interface**

following the feedback from the review phase.

---

## Required Inputs

The following files MUST be available and treated as authoritative:

- **Previous Code** - The code from the last generation iteration
- **Review Feedback** - The issues identified by the reviewer
- **Standards Bundle** - Consolidated standards document
- **Planning Document** - The approved plan for this entity

---

## Revision Guidelines

When revising the code:

1. **Address all critical issues first** - These must be fixed
2. **Address minor issues** - Fix these as well if identified
3. **Do not introduce new issues** - Follow all standards
4. **Preserve working code** - Only change what needs to be fixed

---

## Output Format

Your output MUST consist only of corrected code files:

```java
// FILE: {{ENTITY}}.java
package ...;

@Entity
public class {{ENTITY}} {
    // Corrected implementation
}
```

```java
// FILE: {{ENTITY}}Repository.java
package ...;

public interface {{ENTITY}}Repository extends JpaRepository<{{ENTITY}}, Long> {
    // Corrected implementation
}
```

Only include files that were changed. Use the same format as the generation phase.
