"""Integration tests for prompt assembly.

These tests define the expected end-to-end behavior for prompt assembly:

1. Pass-through mode: profile returns complete prompt string, engine only appends output instructions
2. Two-pass variable substitution:
   - Profile pass: domain variables ({{ENTITY}}, {{TABLE}}, etc.) - already resolved
   - Engine pass: session artifact variables ({{STANDARDS}}, {{PLAN}})

Engine-owned variables:
- {{STANDARDS}} - resolves to standards-bundle.md
- {{PLAN}} - resolves to plan.md
"""

import pytest


class TestPassthroughMode:
    """Pass-through: profile returns string, engine appends output instructions only."""

    def test_engine_does_not_prepend_artifacts(self):
        """Engine should NOT prepend standards/plan content inline."""
        # Profile has already resolved its variables ({{ENTITY}}, {{TABLE}}, etc.)
        profile_prompt = """---
entity: Product
table: app.products
bounded-context: catalog
schema-file: docker/postgres/db/init/01-schema.sql
date: 2025-01-15
---

## Required Attachments

- Schema DDL: @docker/postgres/db/init/01-schema.sql
- Standards: @standards-bundle.md

## Task

Produce a planning document for the domain layer.
"""

        # Engine should NOT prepend "## Standards Bundle\n\n[content...]"
        # The profile's @standards-bundle.md reference is sufficient

        # Expected: profile prompt unchanged, output instructions appended
        expected = """---
entity: Product
table: app.products
bounded-context: catalog
schema-file: docker/postgres/db/init/01-schema.sql
date: 2025-01-15
---

## Required Attachments

- Schema DDL: @docker/postgres/db/init/01-schema.sql
- Standards: @standards-bundle.md

## Task

Produce a planning document for the domain layer.

---

## Output Destination

Save your response to `planning-response.md`
"""
        pytest.skip("Design test - implementation pending")

    def test_no_output_instructions_when_fs_ability_none(self):
        """When fs_ability='none', engine adds nothing."""
        profile_prompt = "## Task\n\nDo something."

        # fs_ability="none" means user will copy/paste - no file instructions needed
        expected = "## Task\n\nDo something."

        pytest.skip("Design test - implementation pending")


class TestEngineVariableSubstitution:
    """Engine substitutes {{STANDARDS}} and {{PLAN}} in second pass."""

    def test_standards_variable(self):
        """{{STANDARDS}} resolves to standards-bundle.md"""
        profile_prompt = """## Required Attachments

- Standards: @{{STANDARDS}}

## Task

Follow the standards.
"""

        expected = """## Required Attachments

- Standards: @standards-bundle.md

## Task

Follow the standards.

---

## Output Destination

Save your response to `planning-response.md`
"""
        pytest.skip("Design test - implementation pending")

    def test_plan_variable(self):
        """{{PLAN}} resolves to plan.md"""
        profile_prompt = """## Required Attachments

- Plan: @{{PLAN}}

## Task

Generate code per the plan.
"""

        expected = """## Required Attachments

- Plan: @plan.md

## Task

Generate code per the plan.

---

## Output Destination

Save your response to `generation-response.md`
"""
        pytest.skip("Design test - implementation pending")

    def test_profile_variables_untouched(self):
        """Engine does not substitute profile-owned variables."""
        # If profile forgot to substitute {{ENTITY}}, engine leaves it alone
        profile_prompt = """entity: {{ENTITY}}
Standards: @{{STANDARDS}}
"""

        expected = """entity: {{ENTITY}}
Standards: @standards-bundle.md

---

## Output Destination

Save your response to `planning-response.md`
"""
        pytest.skip("Design test - implementation pending")


class TestSchemaFilePaths:
    """Schema file path handling.

    Note: Path normalization (backslash → forward slash) happens at CLI input layer.
    The profile uses whatever path it receives - agents/IDEs handle file resolution.
    The @ prefix is a convention but agents work with paths with or without it.
    """

    def test_schema_path_included_in_prompt(self):
        """Schema file path is included in metadata and attachment reference."""
        # Profile receives path (already normalized to /), uses it in prompt
        profile_prompt = """---
entity: Product
schema-file: docker/postgres/db/init/01-schema.sql
---

## Required Attachments

- Schema DDL: @docker/postgres/db/init/01-schema.sql
"""

        expected = """---
entity: Product
schema-file: docker/postgres/db/init/01-schema.sql
---

## Required Attachments

- Schema DDL: @docker/postgres/db/init/01-schema.sql

---

## Output Destination

Save your response to `planning-response.md`
"""
        pytest.skip("Design test - implementation pending")


class TestOutputInstructions:
    """Output instructions appended based on phase and fs_ability."""

    def test_planning_phase_filename(self):
        """Planning phase uses planning-response.md"""
        # phase=PLAN → planning-response.md
        pytest.skip("Design test - implementation pending")

    def test_generation_phase_filename(self):
        """Generation phase uses generation-response.md"""
        # phase=GENERATE → generation-response.md
        pytest.skip("Design test - implementation pending")

    def test_fs_ability_local_write(self):
        """local-write: 'Save your response to `path`'"""
        expected_format = "Save your response to `{path}`"
        pytest.skip("Design test - implementation pending")

    def test_fs_ability_local_read(self):
        """local-read: 'Name your output file `filename`'"""
        expected_format = "Name your output file `{filename}`"
        pytest.skip("Design test - implementation pending")

    def test_fs_ability_write_only(self):
        """write-only: 'Create a downloadable file named `filename`'"""
        expected_format = "Create a downloadable file named `{filename}`"
        pytest.skip("Design test - implementation pending")