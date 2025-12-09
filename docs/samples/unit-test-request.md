---
# METADATA
task-id: Client-Unit-Test
dev: Scott
date: 2025-11-08
test-type: UNIT
class-under-test: com.skillsharbor.backend.controlplane.entities.Client
coverage-mode: <ALL_PUBLIC>
llm-used: <Gemini>
---

## AI Persona & Role

**You are an expert in test-driven development (TDD), with deep knowledge of Java 21, Spring Boot, JUnit 5, AssertJ, and JPA/Hibernate.** Your task is to act as a senior developer on my team, generating a high-quality unit test plan and, upon approval, the corresponding code. You must adhere to all specified standards and protocols.

---

# Unit Test Request Template
_Version: 1.0 (certified)_
_Last updated: 2025-11-03_

## File Attachments

**Standards (always attach):**
> These files are located under docs/testing

- @CP_TESTING_STRATEGY.md
- @TEST_PATTERNS.md
- @TEST_FAQ.md

**Test Infrastructure (always attach):**
> These files are located under backend/app/src/test/java/com/skillsharbor/backend/controlplane/test

- @TestUtils.java

**Class Under Test:**
- @Client.java

**Schema DDL (required for entity tests):**
> **For entity unit tests:** Attach the schema DDL so AI can verify the entity correctly represents the table structure (column types, constraints, relationships).
> **For non-entity classes:** Not needed.
>
> V1 schema: backend/db/controlplane/src/main/resources/db/migration

- @V1__baseline_schema.sql (if testing an entity)


**VALIDATION:** If any required file is missing/unreadable, AI must STOP and emit:
`VALIDATION FAILED: missing files: <list>`

---

## AI Task Phases (MANDATORY)

**PHASE 1 – TEST PLAN ONLY**
Produce a concise plan covering:
- Method inventory and behaviors to test (based on `coverage-mode`)
- Test class structure (e.g., `@Nested` sections, test names)
- Edge cases, guards (exception **type + message**), state transitions & idempotency
- What will **not** be tested (and why)
- Files/helpers you'll rely on (e.g., `TestUtils`)
- Open questions for the developer (if any)

**Do not** emit any files.

**STOP after creating the inventory and summary. Wait for developer feedback. Only continue if the developer writes exactly: 'APPROVED — proceed to Phase 2'.**

### Handling Plan Revisions

1. If the developer response is anything other than the exact approval string, treat it as a request to revise the plan.
2. Generate a **new, complete test plan** that fully incorporates the developer’s feedback. Do not emit any code.
3. Present the revised plan clearly, replacing only the plan portion (not the entire prompt structure).
4. After presenting the revised plan, **stop and wait for explicit approval**.  
   Proceed to Phase 2 only when the developer writes exactly:
   > `APPROVED — proceed to Phase 2`


**PHASE 2 – CODE EMISSION**
Generate the test file(s) AND generation context using the Output Format below.

---

## Test Configuration

**Coverage mode:** [Filled from metadata: ALL_PUBLIC or LIMIT]

**Methods to cover** (if LIMIT):
- [ ] `method1(Type arg) -> ReturnType`
- [ ] `method2(Type arg) -> ReturnType`

**Must-Cover Edge Cases** (optional - dev can add specific cases):
- [ ] Null handling in constructor
- [ ] Boundary condition in validation

---

## Constraints (MANDATORY)

> Do **not** re-test `BaseEntity` public methods here (covered by `BaseEntityTest`). Only cover entity-specific behavior or overrides.

**Environment:**
- No Spring context, no DB, no I/O
- No Testcontainers or external dependencies
- Add `@Tag("unit")` to test class

**Mocking:**
- Mock external boundaries only (repos, HTTP clients, external services)
- **Never mock JPA/Hibernate** (those are external boundaries tested in integration tests)

**Helpers:**
- Use `TestUtils` for instantiation if constructors are protected
- Use `TestUtils` to invoke protected lifecycle methods (e.g., `onCreate()`)

**Patterns:**
- AAA structure (Arrange, Act, Assert)
- Use AssertJ (`assertThat(...)`)
- Use descriptive `@DisplayName` strings

**Unit-Specific Coverage:**
- **Normalization**: Test **only if implemented in Java** (constructor/setters). If DB-only (triggers), skip.
- **Immutability**: Assert identifiers (`code`, `publicId`) don't change after construction
- **Optional fields**: Verify optional attributes accept `null` (construction + setters)
- **State transitions**: Cover transitions and **idempotency** (e.g., calling `activate()` twice)
- **Equality/HashCode**: If overridden by the entity, test the contract (same instance, different type, etc.). If not overridden, do not test.
- **toString**: Assert class name and `publicId` presence. **Avoid exact full-string equality** (brittle)
- **Lifecycle**: May reflectively invoke `onCreate()` to assert `publicId` set and `createdAt == updatedAt` at creation. **No timestamp progression** assertions.

---

## Test Scope

**Test these:**
- Constructor logic and field initialization
- State management methods (activate, deactivate, etc.)
- Business logic methods (calculations, transformations)
- Validation logic (input checks, preconditions)
- Edge cases (nulls, boundaries, empty collections)
- Equality, hashCode, toString contracts

**Skip these:**
- Database persistence behavior (integration test concern)
- Spring framework features (autowiring, transactions, etc.)
- DB-layer normalization (trigger-based)
- Timestamp progression beyond creation
- Framework internals (JPA lifecycle, proxy behavior)

---

## Pre-Emission Validation (AI MUST PERFORM)

Before generating code, verify and document in summary:

1. ✅ **Method inventory complete**: List all public methods with full signatures
2. ✅ **File access confirmed**: All referenced files exist or source pasted inline
3. ✅ **API correctness**: Method calls match actual signatures from source
4. ✅ **Test tag present**: Class has `@Tag("unit")` annotation
5. ✅ **No I/O dependencies**: No Spring annotations, no DB setup, no Testcontainers
6. ✅ **Mocking boundaries correct**: Only external boundaries mocked (no JPA mocking)
7. ✅ **Normalization ownership**: If normalization tests exist, confirmed Java-owned (not DB triggers)
8. ✅ **Immutability coverage**: Identifier immutability tested where applicable
9. ✅ **Optional field handling**: Null acceptance verified for optional attributes
10. ✅ **State transition idempotency**: Repeated calls to state methods tested
11. ✅ **Equality/hashCode coverage**: Equality/hashCode logic handled: Tests correctly generated if overridden, and correctly skipped if not.
12. ✅ **Non-brittle toString**: Presence checks used (not exact string matching)
13. ✅ **No timestamp progression**: Only creation-time equality checked (if applicable)
14. ✅ **Java syntax validated**: All code follows Java 21 syntax (explicit types, semicolons, new keyword, getX() methods, throws clauses)
15. ✅ **BaseEntity methods excluded**: Confirmed that no tests are generated for BaseEntity methods unless the entity explicitly overrides them (e.g., equals, hashCode).

**If any validation fails:** Emit markdown summary ending with `*** END OF MARKDOWN SUMMARY ***` followed by `VALIDATION FAILED` section listing each failed check. Do NOT emit code.

### Pre-Emission Validation — Required Attachments (HARD STOP)

The following attachments are **mandatory**. If any are missing, output:

`VALIDATION FAILED: missing files: <comma-separated list>`

and **stop**.

- `@CP_TESTING_STRATEGY.md`
- `@TEST_PATTERNS.md`
- `@TEST_FAQ.md`
- `@BaseIntegrationTest.java`
- `@TestDataFactory.java`
- `@TestUtils.java`
- Class Under Test (this request’s `class-under-test`)
- **Conditional:** If the class under test is an **entity** (its FQN contains `.entities.`), also require the schema DDL (e.g., `@V1__baseline_schema.sql`). If not an entity, this item is **not required**.

---

## Output Format (REQUIRED FOR ALL AIs)

**CRITICAL: Java Only - No Kotlin**
- All code must be Java 21
- Do NOT generate Kotlin code
- Use JUnit 5 + AssertJ (Java syntax)

**CRITICAL: Java Syntax Adherence**

All generated code must strictly follow Java 21 syntax. Before emitting code, internally validate against this checklist:
- ✅ **Explicit Types**: All variable and method declarations must have explicit types first (e.g., `String name;`, `void myMethod()`). Do NOT use Kotlin-style `val name: String` or `fun myMethod()`.
- ✅ **Semicolons**: Every statement must end with a semicolon (`;`).
- ✅ **new Keyword**: Object instantiation must use the `new` keyword (e.g., `Tier tier = new Tier(...)`).
- ✅ **JavaBean Getters**: Getters must follow the `getX()` convention (e.g., `tier.getName()`). Do NOT use direct property access like `tier.name` in assertions unless it's a public field.
- ✅ **throws Clause**: Test methods that can throw checked exceptions must include a `throws` clause (e.g., `void myTest() throws Exception`).

**CRITICAL - Filename Markers:**
- Use ONLY the filename in markers: `<<<FILE: TierTest.java>>>`
- Do NOT include any path: ~~`<<<FILE: src/test/.../TierTest.java>>>`~~
- The extraction script will place files based on the --output-dir parameter

**CRITICAL: File Creation and Verification Protocol**

After generating the content for the bundle, you must follow this exact, non-negotiable protocol to save the file:
1. Determine Path: Determine the absolute path for the output bundle file based on the <Class> and <test-type> from the METADATA. The format is: backend/ai-artifacts/<Class>/<test-type>/gen-bundle.md.
2. Write File: Execute the write_file command to create the bundle at the determined absolute path.
3. Verify Write: Immediately after the write_file command, execute the read_file command on the exact same absolute path. This is a mandatory verification step.
4. Report Outcome:
- On Success: If the read_file command returns the content successfully, you can report to the user that the file has been created at the specified location.
- On Failure: If the read_file command returns a "file not found" error, you must: a.  Report that the initial write failed verification. b.  Immediately retry the write_file command (Step 2). c.  Retry the read_file verification (Step 3). d.  Do not end the turn until the read_file verification succeeds.

**Markdown Output Format:**
Output a single Markdown file in one fenced code block starting with \`\`\`markdown.
- Use 4-space indentation for code examples (no nested backticks)
- Use *** for horizontal rules (not ---)
- End with \`\`\` on its own line

This format ensures compatibility with the extraction script and proper display in all AI interfaces.

**Bundle structure:** Single fenced markdown block with filename-only markers and 4-space indented code.

```
<<<FILE: YourClassTest.java>>>

    package com.skillsharbor...;
    
    import org.junit.jupiter.api.Tag;
    [4-space indented code]

<<<FILE: gen-context.md>>>

    # Generation Context
    [4-space indented content]
```

**Files to generate:**

**1. YourClassTest.java** (test code)
- **Java 21 only - NO KOTLIN**
- JUnit 5 + AssertJ (Java syntax)
- Package matches source
- `@Tag("unit")` on class

**2. gen-context.md** (generation context)
- Standards Applied (cite exact sections)
- Design Decisions (why choices were made)
- Method Inventory (tests generated + not tested)
- Coverage Summary

**Formatting rules:**
- Marker on its own line (no code on same line)
- Code starts next line with 4-space indentation
- No triple backticks inside the bundle
- Filename only (no paths)

**Important:** The helper script will extract these files and embed `gen-context.md` into the code review request. Do NOT create a `cr-review-request.md` file (the script handles this).

**STOP after creating the inventory and summary. Wait for developer feedback. Only continue if the developer writes exactly: 'APPROVED — proceed to Phase 2'.**

---

## Instructions to AI

> **Conflict Resolution**: If any instruction in this request conflicts with the attached standards documents (`CP_TESTING_STRATEGY.md`, `TEST_PATTERNS.md`, `TEST_FAQ.md`), **the standards win**. Cite the standards rather than restating them.

**When you receive this request:**

1. ✅ Load and read all attached files (standards + source code)
2. ✅ Verify metadata: test-type=UNIT, class-under-test present, coverage-mode specified
3. ✅ Perform pre-emission validation (all 14 checks above)
4. ✅ Generate test file(s) following all constraints
    - Organize tests logically (by method or concern)
    - Use `@Nested` classes for complex entities
    - Cover all behavioral expectations from Constraints section
    - **Use Java 21 only - NO Kotlin**
5. ✅ Generate gen-context.md with full context about your design
6. ✅ Emit all outputs as specified in the Output Generation and Delivery Protocol (Universal) section.

**Begin generation now. Do not ask for confirmation.**
