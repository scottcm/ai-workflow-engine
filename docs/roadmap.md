# AI Workflow Engine — Roadmap (Milestones)

This roadmap is organized around **capability milestones**, not dates.
Statuses reflect current progress and intended sequencing.
Dates are intentionally omitted; this is a side project intended to:
- support Skills Harbor development, and
- serve as a portfolio-quality engineering artifact.

---

## M1 — Foundation ✅ Complete

**Goal:** Establish architectural invariants and core scaffolding.

- Core repository structure
- Architecture Decision Records (ADRs)
- Workflow state model and invariants
- Test framework and fixtures
- Baseline documentation

**Exit criteria:** Core domain concepts are defined, testable, and stable.

---

## M2 — First Profile: `jpa-mt` ✅ Complete

**Goal:** Prove the profile/plugin model with a real, non-trivial profile.

- `jpa-mt` profile implementation
- Bundle extractor
- File writer
- Template renderer
- Profile-specific unit tests

**Exit criteria:** A complete vertical slice can be generated via a profile.

---

## M3 — Patterns & Pipeline ✅ Complete

**Goal:** Validate the immutable, profile-driven generation pipeline.

- Immutable generation step (`process_generation_response`)
- Profile delegation pattern
- Manual prompt rendering helper
- Manual code extraction helper (TDD-driven)
- Phase 3 smoke test (CLI-level workflow guard)

**Exit criteria:** End-to-end generation works reliably in a human-in-the-loop workflow.

---

## M4 — Review & Revision Loop ✅ Complete

**Goal:** Support iterative refinement of generated artifacts.

- Review artifacts and feedback capture
- Revision prompts and iteration handling
- Clear separation between generation, review, and revision steps

**Exit criteria:** A full generate → review → revise loop is supported.

---

## DEFERRED (post M5) — Orchestration Engine & State Validation ⏳ Planned

**Goal:** Automate workflow execution while hardening state correctness.

- Orchestration logic (no manual steps)
- Resume / retry / failure handling
- **Adopt Pydantic for WorkflowState validation and serialization**
- Schema versioning and forward-compatibility strategy

**Exit criteria:** Workflows can run unattended with strong state guarantees.

---

## M6 — CLI & Polish ⏳ Planned

**Goal:** Provide a production-quality command-line interface.

- Consolidated CLI entrypoint
- Subcommands (new, run, resume, status, etc.)
- Improved argument validation and UX
- **Adopt Click for CLI implementation**
- CLI-focused tests and documentation

**Exit criteria:** The system is usable via a clean, documented CLI.

---

## M7 — Editor / Tooling Integration ⏳ Planned

**Goal:** Improve developer ergonomics.

- VS Code extension integration
- Prompt preview and artifact inspection
- Workflow visibility from the editor

**Exit criteria:** Core workflows are accessible from common developer tools.

---

## Enhancements (Post-MVP)

These are desirable but not required for initial completion.

- Additional generation profiles
- Plugin discovery / registration
- Advanced validation and linting
- Performance optimizations
- Packaging / distribution improvements

---

## Notes

- Milestones represent **capability boundaries**, not rigid phases.
- Status reflects current reality, not aspirational timelines.
- Architectural decisions are documented separately in ADRs.
