---
# METADATA
task-id: {{TASK_ID}}
dev: {{DEV}}
date: {{DATE}}
entity: {{ENTITY}}
scope: {{SCOPE}}
table: {{TABLE}}
bounded-context: {{BOUNDED_CONTEXT}}
session-id: {{SESSION_ID}}
profile: {{PROFILE}}
iteration: {{ITERATION}}
schema-file: {{SCHEMA_FILE}}
---

## Purpose of This Prompt

This prompt is part of a **multi-phase AI workflow**.  
Your behavior, role, required inputs, and output expectations are defined by the **phase-specific guidelines** included below.

You MUST read and follow all included sections in order.

---

## File Attachments (General Rules)

This prompt may reference **required** and **optional** input artifacts.

Artifacts may be provided via:
- file attachment
- IDE/agent file reference
- copy-paste (when attachments are not supported)

The **phase-specific guidelines** define which inputs are required for this prompt.

---

## Validation Contract

If any input explicitly marked as **required** by the phase-specific guidelines is missing, you MUST:

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
