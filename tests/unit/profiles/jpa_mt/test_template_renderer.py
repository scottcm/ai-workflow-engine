"""Unit tests for template rendering with include resolution and placeholder filling."""

import pytest
from pathlib import Path
from datetime import datetime
from profiles.jpa_mt.jpa_mt_profile import JpaMtProfile
from profiles.jpa_mt.template_renderer import TemplateRenderer
from aiwf.domain.models.workflow_state import WorkflowPhase
import yaml


@pytest.fixture
def profile():
    """Create a JpaMtProfile instance with test configuration."""
    # Load actual config from profiles/jpa-mt/config.yml
    # We need to find the project root to locate the file reliably
    project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
    config_path = project_root / "profiles/jpa_mt/config.yml"
    
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    # Pass the resolved config_path and unpacked config to JpaMtProfile
    return JpaMtProfile(config_path=config_path, **config)


@pytest.fixture
def renderer(profile):
    """Create a TemplateRenderer instance."""
    return TemplateRenderer(profile)


@pytest.fixture
def valid_context():
    """Provide valid context with all required placeholders."""
    return {
        "TASK_ID": "TEST-001",
        "DEV": "Scott",
        "DATE": "2024-12-09",
        "ENTITY": "Tier",
        "SCOPE": "domain",
        "TABLE": "global.tiers",
        "BOUNDED_CONTEXT": "catalog",
        "SESSION_ID": "test-session-001",
        "PROFILE": "jpa-mt",
        "ITERATION": "1",
    }


def test_render_template_resolves_includes(renderer, valid_context):
    """Test that renderer resolves {{include:}} directives."""
    result = renderer.render_template(
        WorkflowPhase.INITIALIZED,  # planning phase
        "domain",
        valid_context
    )
    
    # All includes should be resolved
    assert "{{include:" not in result
    
    # Content from included files should be present (based on actual files in the repo)
    # _shared/base.md usually has metadata block or specific headers
    # We check for generic content likely to be in the base includes
    # Adjust assertions if base files content changes significantly
    assert "## AI Persona & Role" in result or "# Domain Layer Planning Request" in result


def test_render_template_fills_placeholders(renderer, valid_context):
    """Test that renderer fills {{PLACEHOLDER}} variables."""
    result = renderer.render_template(
        WorkflowPhase.INITIALIZED,
        "domain",
        valid_context
    )
    
    # All placeholders should be filled
    assert "{{ENTITY}}" not in result
    assert "{{TABLE}}" not in result
    assert "{{TASK_ID}}" not in result
    
    # Values should be present
    # Case sensitive check might fail if template uses 'Entity:' vs 'entity:'
    # Check lower case to be safer or multiple variations
    lower_result = result.lower()
    assert "tier" in lower_result
    assert "global.tiers" in lower_result
    assert "test-001" in lower_result
    assert "catalog" in lower_result


def test_render_template_missing_required_context(renderer):
    """Test that renderer raises KeyError for missing required fields."""
    incomplete_context = {
        "ENTITY": "Tier",
        "TABLE": "global.tiers",
        # Missing: TASK_ID, DEV, DATE, etc.
    }
    
    with pytest.raises(KeyError) as exc_info:
        renderer.render_template(
            WorkflowPhase.INITIALIZED,
            "domain",
            incomplete_context
        )
    
    error_message = str(exc_info.value)
    assert "Missing required context keys" in error_message
    assert "TASK_ID" in error_message


def test_render_template_invalid_phase(renderer, valid_context):
    """Test that renderer handles invalid phase gracefully."""
    # WorkflowPhase.COMPLETE usually maps to nothing in JpaMtProfile
    with pytest.raises(ValueError):
        renderer.render_template(
            WorkflowPhase.COMPLETE,
            "domain",
            valid_context
        )


def test_render_template_invalid_scope(renderer, valid_context):
    """Test that renderer handles invalid scope gracefully."""
    with pytest.raises(ValueError):
        renderer.render_template(
            WorkflowPhase.INITIALIZED,
            "invalid-scope",  # Not defined in config
            valid_context
        )


def test_fill_placeholders_all_replaced(renderer):
    """Test that _fill_placeholders replaces all occurrences."""
    content = """
    Entity: {{ENTITY}}
    Table: {{TABLE}}
    Another entity reference: {{ENTITY}}
    """
    
    context = {
        "TASK_ID": "TEST", "DEV": "Test", "DATE": "2024-12-09",
        "ENTITY": "Tier", "SCOPE": "domain", "TABLE": "global.tiers",
        "BOUNDED_CONTEXT": "catalog", "SESSION_ID": "test",
        "PROFILE": "jpa-mt", "ITERATION": "1"
    }
    
    result = renderer._fill_placeholders(content, context)
    
    # Both occurrences of {{ENTITY}} should be replaced
    assert result.count("Tier") == 2
    assert "{{ENTITY}}" not in result
    assert "{{TABLE}}" not in result


def test_integration_full_workflow(renderer):
    """Integration test: Full template rendering workflow."""
    context = {
        "TASK_ID": "JIRA-456",
        "DEV": "Scott McGee",
        "DATE": datetime.now().strftime("%Y-%m-%d"),
        "ENTITY": "Product",
        "SCOPE": "domain",
        "TABLE": "catalog.products",
        "BOUNDED_CONTEXT": "catalog",
        "SESSION_ID": "20241209-143045-abc",
        "PROFILE": "jpa-mt",
        "ITERATION": "1",
    }
    
    # Render template
    result = renderer.render_template(
        WorkflowPhase.INITIALIZED,
        "domain",
        context
    )
    
    # Comprehensive validation
    assert len(result) > 100  # Should be substantial content
    assert "{{include:" not in result
    assert "{{ENTITY}}" not in result
    assert "{{TABLE}}" not in result
    
    # Verify context values
    assert "JIRA-456" in result
    assert "Scott McGee" in result
    assert "Product" in result
    assert "catalog.products" in result
    
def test_render_template_composes_layered_templates(renderer, valid_context):
    """
    Ensure the planning/domain.md template composes the layered templates correctly:

    - Shared base (_shared/base.md)       → metadata, persona, etc.
    - Shared fallbacks (_shared/fallback-rules.md) → fallback rules section
    - Phase-specific guidelines (_phases/planning-guidelines.md)
    - Scope-specific content (planning/domain.md)

    All include directives should be resolved, and content from each layer should
    appear in the final rendered prompt.
    """
    result = renderer.render_template(
        WorkflowPhase.INITIALIZED,
        "domain",
        valid_context,
    )

    # All includes must be fully resolved
    assert "{{include:" not in result

    # Scope-specific: domain.md
    assert "Domain Layer Planning Request" in result or "domain layer" in result.lower()

    # Phase-specific: planning-guidelines.md
    assert "Planning Phase Guidelines" in result or "planning phase" in result.lower()

    # Shared fallback rules: _shared/fallback-rules.md
    assert "Fallback Rules" in result or "fallback rules" in result.lower()

    # Shared base: base.md (metadata block or task-id line)
    assert "# METADATA" in result or "task-id:" in result.lower()
