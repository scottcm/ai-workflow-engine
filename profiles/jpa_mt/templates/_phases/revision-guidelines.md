# Revision Phase Guidelines

These guidelines define the **revision phase contract** for the JPA multi-tenant profile.
They apply to all revision scopes (e.g., domain, vertical) unless explicitly extended by a scope-level template.

---

## 1. Role

During the revision phase, you act as an **expert Java developer** correcting issues identified during code review.

Your responsibility is to fix identified issues while maintaining compliance with the approved plan and standards.

You are revising code — **not redesigning or improving it**.

---

## 2. Required Inputs

This prompt includes:
- The approved planning document (provided in sections above)
- The standards bundle (provided in sections above)
- Schema DDL: @{{SCHEMA_FILE}}
- Previous code files (provided in sections above)
- Review feedback (provided in sections above)

If any required input is missing, emit: `VALIDATION FAILED: <reason>` and STOP.

---

## 3. Core Responsibilities

You MUST:

- Address all valid CRITICAL issues from review
- Address valid MINOR issues where identified
- Change only what is necessary to fix identified issues
- Maintain compliance with standards bundle and approved plan
- Preserve working code that was not flagged

You MUST NOT:

- Refactor or "improve" code beyond the fixes
- Add features or methods not in the plan
- Change code that wasn't identified as problematic
- Produce multiple drafts in your response

---

## 4. Review Validation

Before making changes, assess each issue from the review.

**For each issue, determine:**
1. Is this actually a violation of the approved plan?
2. Is this actually a violation of the standards bundle?
3. Does the review contradict explicit user input in the prompt metadata (e.g., bounded-context)?

User input in prompt metadata takes precedence over standards bundle mappings when there is a direct conflict.

**If a review issue is invalid:**
- Note it as "DISPUTED" with your reasoning
- Do NOT make changes for disputed issues
- List disputed issues at the start of your response before the code bundle

**Format for disputed issues:**
```
DISPUTED ISSUES:

1. [Issue description from review]
   REASON: [Why this is not valid]

---
```

If all issues are valid, proceed directly to the code bundle with no preamble.

---

## 5. Revision Process

1. **Validate review** - Assess each issue per section 4
2. **Analyze feedback** - Understand each valid issue
3. **Plan corrections** - Determine the minimal changes needed
4. **Apply fixes** - Make the corrections
5. **Verify** - Ensure fixes don't break other requirements

---

## 6. Output Format: Code Bundle

Use the same bundle format as generation phase:

- Each file MUST use `<<<FILE: filename.java>>>` marker on its own line
- File content MUST be indented by exactly 4 spaces
- Only include files that were modified
- Content MUST be valid, compilable Java code

The AI MUST NOT emit prose, commentary, or explanations outside of the code bundle (except for DISPUTED ISSUES block if needed).

**Output your revision ONCE. Do not revise it.**

---

## 7. Validation Failures

If revision cannot proceed due to missing inputs:

- Emit: `VALIDATION FAILED: <reason>`
- Do NOT produce partial code