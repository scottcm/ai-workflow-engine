---
entity: {{ENTITY}}
scope: {{SCOPE}}
table: {{TABLE}}
bounded-context: {{BOUNDED_CONTEXT}}
schema-file: {{SCHEMA_FILE}}
---

## Required Attachments

- Schema DDL: @{{SCHEMA_FILE}}
- Standards Bundle: @{{STANDARDS}}

---

## Purpose of This Prompt

This prompt is part of a **multi-phase AI workflow**.
Your behavior, role, required inputs, and output expectations are defined by the **phase-specific guidelines** included below.

You MUST read and follow all included sections in order.

---

## Validation Contract

If any required attachment above is missing, you MUST:

```
VALIDATION FAILED: missing required inputs: <list of missing inputs>
```

Then STOP.
Do not infer missing information.
Do not proceed with partial context.

---

## Standards Authority Rule

If there is any conflict between:
- instructions in this prompt
- fallback rules
- or phase-specific guidance

and the **standards-bundle**, the **standards-bundle ALWAYS takes precedence**.

If the standards-bundle is silent on a topic:
- Follow the fallback rules
- If ambiguity remains, request clarification rather than inventing behavior

---
