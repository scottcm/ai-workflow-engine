"""Tests for JpaMtProfile."""

import pytest
from pathlib import Path
from unittest.mock import patch

from aiwf.domain.models.workflow_state import WorkflowStatus
from profiles.jpa_mt.profile import JpaMtProfile
from profiles.jpa_mt.config import JpaMtConfig, StandardsConfig, StandardsSource


class TestConditionalProcessing:
    """Test conditional template processing."""

    @pytest.fixture
    def profile(self):
        """Create a JpaMtProfile instance."""
        return JpaMtProfile()

    def test_if_block_with_defined_var(self, profile):
        """{{#if var}} includes content when var is defined and non-empty."""
        text = "Hello {{#if name}}{{name}}{{/if}}!"
        variables = {"name": "World"}
        result = profile._resolve_variables(text, variables)
        assert result == "Hello World!"

    def test_if_block_with_undefined_var(self, profile):
        """{{#if var}} excludes content when var is undefined."""
        text = "Hello {{#if name}}{{name}}{{/if}}!"
        variables = {}
        result = profile._resolve_variables(text, variables)
        assert result == "Hello !"

    def test_if_block_with_empty_var(self, profile):
        """{{#if var}} excludes content when var is empty string."""
        text = "Hello {{#if name}}{{name}}{{/if}}!"
        variables = {"name": ""}
        result = profile._resolve_variables(text, variables)
        assert result == "Hello !"

    def test_unless_block_with_undefined_var(self, profile):
        """{{#unless var}} includes content when var is undefined."""
        text = "{{#unless entity_extends}}No base class{{/unless}}"
        variables = {}
        result = profile._resolve_variables(text, variables)
        assert result == "No base class"

    def test_unless_block_with_defined_var(self, profile):
        """{{#unless var}} excludes content when var is defined."""
        text = "{{#unless entity_extends}}No base class{{/unless}}"
        variables = {"entity_extends": "BaseEntity"}
        result = profile._resolve_variables(text, variables)
        assert result == ""

    def test_nested_conditionals(self, profile):
        """Nested conditionals are processed correctly."""
        text = "{{#if a}}A{{#if b}}B{{/if}}{{/if}}"
        variables = {"a": "yes", "b": "yes"}
        result = profile._resolve_variables(text, variables)
        assert result == "AB"

    def test_nested_conditionals_outer_false(self, profile):
        """Nested conditionals - outer false excludes inner."""
        text = "{{#if a}}A{{#if b}}B{{/if}}{{/if}}"
        variables = {"b": "yes"}  # a undefined
        result = profile._resolve_variables(text, variables)
        assert result == ""

    def test_inheritance_pattern(self, profile):
        """Test typical inheritance pattern with extends/implements."""
        text = "public class {{entity_name}}{{#if entity_extends}} extends {{entity_extends}}{{/if}}{{#if entity_implements}} implements {{entity_implements}}{{/if}} {"

        # With both extends and implements
        variables = {
            "entity_name": "User",
            "entity_extends": "BaseEntity",
            "entity_implements": "Serializable"
        }
        result = profile._resolve_variables(text, variables)
        assert result == "public class User extends BaseEntity implements Serializable {"

        # With only extends
        variables = {"entity_name": "User", "entity_extends": "BaseEntity"}
        result = profile._resolve_variables(text, variables)
        assert result == "public class User extends BaseEntity {"

        # With neither
        variables = {"entity_name": "User"}
        result = profile._resolve_variables(text, variables)
        assert result == "public class User {"

    def test_undefined_var_becomes_empty(self, profile):
        """Undefined variables become empty strings."""
        text = "Value: [{{undefined}}]"
        variables = {}
        result = profile._resolve_variables(text, variables)
        assert result == "Value: []"

    def test_multiline_conditional(self, profile):
        """Conditional blocks can span multiple lines."""
        text = """Header
{{#if section}}
## Section
Content here
{{/if}}
Footer"""
        variables = {"section": "yes"}
        result = profile._resolve_variables(text, variables)
        assert "## Section" in result
        assert "Content here" in result

        variables = {}
        result = profile._resolve_variables(text, variables)
        assert "## Section" not in result
        assert "Content here" not in result


class TestProcessReviewResponse:
    """Test process_review_response method."""

    @pytest.fixture
    def profile(self):
        """Create a JpaMtProfile instance."""
        return JpaMtProfile()

    def test_pass_verdict_returns_success(self, profile):
        """PASS verdict returns SUCCESS status."""
        content = """
# Code Review

@@@REVIEW_META
verdict: PASS
issues_total: 0
issues_critical: 0
missing_inputs: 0
@@@
"""
        result = profile.process_review_response(content)
        assert result.status == WorkflowStatus.SUCCESS
        assert result.approved is True
        assert result.metadata["verdict"] == "PASS"
        assert "PASS | issues=0" in result.messages[0]

    def test_fail_verdict_returns_failed(self, profile):
        """FAIL verdict returns FAILED status."""
        content = """
# Code Review

@@@REVIEW_META
verdict: FAIL
issues_total: 3
issues_critical: 1
missing_inputs: 0
@@@
"""
        result = profile.process_review_response(content)
        assert result.status == WorkflowStatus.FAILED
        assert result.approved is False
        assert result.metadata["verdict"] == "FAIL"
        assert result.metadata["issues_total"] == 3
        assert result.metadata["issues_critical"] == 1
        assert "FAIL | issues=3" in result.messages[0]

    def test_empty_content_returns_error(self, profile):
        """Empty content returns ERROR status."""
        result = profile.process_review_response("")
        assert result.status == WorkflowStatus.ERROR
        assert "Empty review response" in result.error_message

    def test_missing_metadata_returns_error(self, profile):
        """Missing @@@REVIEW_META block returns ERROR status."""
        content = "Just a review without metadata."
        result = profile.process_review_response(content)
        assert result.status == WorkflowStatus.ERROR
        assert "@@@REVIEW_META" in result.error_message

    def test_invalid_verdict_returns_error(self, profile):
        """Invalid verdict returns ERROR status."""
        content = """
@@@REVIEW_META
verdict: MAYBE
issues_total: 0
issues_critical: 0
missing_inputs: 0
@@@
"""
        result = profile.process_review_response(content)
        assert result.status == WorkflowStatus.ERROR
        assert "Invalid verdict" in result.error_message

    def test_metadata_fields_in_result(self, profile):
        """All metadata fields are included in result."""
        content = """
@@@REVIEW_META
verdict: PASS
issues_total: 2
issues_critical: 0
missing_inputs: 1
@@@
"""
        result = profile.process_review_response(content)
        assert result.metadata["verdict"] == "PASS"
        assert result.metadata["issues_total"] == 2
        assert result.metadata["issues_critical"] == 0
        assert result.metadata["missing_inputs"] == 1


class TestGetStandardsConfig:
    """Test get_standards_config method."""

    def test_uses_explicit_source_path(self, tmp_path):
        """Explicit source path takes priority."""
        source = StandardsSource(type="local", path=str(tmp_path / "rules"))
        config = JpaMtConfig(
            standards=StandardsConfig(sources=[source])
        )
        profile = JpaMtProfile(config=config)

        result = profile.get_standards_config()

        assert result["rules_path"] == str(tmp_path / "rules")

    def test_uses_default_rules_path_when_no_sources(self, tmp_path):
        """default_rules_path is used when sources is empty."""
        config = JpaMtConfig(
            standards=StandardsConfig(
                default_rules_path=str(tmp_path / "default-rules")
            )
        )
        profile = JpaMtProfile(config=config)

        result = profile.get_standards_config()

        assert result["rules_path"] == str(tmp_path / "default-rules")

    def test_source_takes_priority_over_default(self, tmp_path):
        """Explicit source takes priority over default_rules_path."""
        source = StandardsSource(type="local", path=str(tmp_path / "explicit"))
        config = JpaMtConfig(
            standards=StandardsConfig(
                sources=[source],
                default_rules_path=str(tmp_path / "default")
            )
        )
        profile = JpaMtProfile(config=config)

        result = profile.get_standards_config()

        assert result["rules_path"] == str(tmp_path / "explicit")

    def test_falls_back_to_profile_rules_dir(self, tmp_path):
        """Falls back to profile's rules/ directory if it exists."""
        config = JpaMtConfig()  # No sources, no default_rules_path
        profile = JpaMtProfile(config=config)

        # Mock the profile's rules directory to exist
        with patch.object(Path, "exists", return_value=True):
            result = profile.get_standards_config()

        # Should return profile's rules/ path (existence mocked)
        assert "rules_path" in result
        # Path should end with 'rules' or be the profile directory's rules
        if result["rules_path"]:
            assert "rules" in result["rules_path"]

    def test_returns_none_when_no_rules_found(self):
        """Returns None rules_path when no rules directory exists."""
        config = JpaMtConfig()  # No sources, no default_rules_path
        profile = JpaMtProfile(config=config)

        # Mock the profile's rules directory to NOT exist
        with patch.object(Path, "exists", return_value=False):
            result = profile.get_standards_config()

        assert result["rules_path"] is None


class TestFromConfigFile:
    """Test from_config_file factory method."""

    def test_from_config_file_with_valid_path(self, tmp_path):
        """Factory loads config from specified path."""
        config_file = tmp_path / "config.yml"
        config_file.write_text(
            """base_package: com.test.app
assume_answers: true
"""
        )

        profile = JpaMtProfile.from_config_file(config_file)

        assert profile.config.base_package == "com.test.app"
        assert profile.config.assume_answers is True

    def test_from_config_file_with_string_path(self, tmp_path):
        """Factory accepts string path."""
        config_file = tmp_path / "config.yml"
        config_file.write_text("base_package: com.string.path\n")

        profile = JpaMtProfile.from_config_file(str(config_file))

        assert profile.config.base_package == "com.string.path"

    def test_from_config_file_missing_raises_error(self, tmp_path):
        """Factory raises FileNotFoundError for missing explicit path."""
        missing_path = tmp_path / "nonexistent.yml"

        with pytest.raises(FileNotFoundError) as exc_info:
            JpaMtProfile.from_config_file(missing_path)

        assert "nonexistent.yml" in str(exc_info.value)

    def test_from_config_file_none_uses_default(self):
        """Factory with None returns profile with default config."""
        # When default config.yml doesn't exist, should return default config
        with patch.object(Path, "exists", return_value=False):
            profile = JpaMtProfile.from_config_file(None)

        # Should have default values
        assert profile.config.base_package == "com.example.app"
        assert profile.config.assume_answers is False

    def test_constructor_no_file_io(self):
        """Constructor with None config doesn't do file I/O."""
        # This verifies the refactored constructor doesn't load files
        profile = JpaMtProfile()

        # Should have default config without file I/O
        assert profile.config.base_package == "com.example.app"


class TestAIProviderProperty:
    """Tests for ai_provider lazy initialization (ADR-0010)."""

    def test_ai_provider_returns_none_when_not_configured(self):
        """ai_provider returns None when config has no ai_provider."""
        profile = JpaMtProfile()  # Default config has ai_provider=None

        assert profile.ai_provider is None
        assert profile._ai_provider is None  # Cache not populated

    def test_ai_provider_lazy_creates_provider(self):
        """ai_provider creates provider on first access when configured."""
        from unittest.mock import MagicMock, patch

        config = JpaMtConfig(ai_provider="claude-code")
        profile = JpaMtProfile(config=config)

        mock_provider = MagicMock()
        with patch(
            "aiwf.domain.providers.provider_factory.AIProviderFactory.create",
            return_value=mock_provider,
        ) as mock_create:
            # First access should create provider
            provider = profile.ai_provider

            assert provider is mock_provider
            mock_create.assert_called_once_with("claude-code")

            # Second access should return cached provider (no new create call)
            provider2 = profile.ai_provider
            assert provider2 is provider
            mock_create.assert_called_once()  # Still just one call

    def test_ai_provider_can_inject_mock_for_testing(self):
        """Tests can inject mock directly via _ai_provider."""
        from unittest.mock import MagicMock

        profile = JpaMtProfile()
        mock_provider = MagicMock()

        # Inject mock directly
        profile._ai_provider = mock_provider

        # Property returns injected mock
        assert profile.ai_provider is mock_provider

    def test_ai_provider_config_loads_from_yaml(self, tmp_path):
        """ai_provider field loads correctly from YAML config."""
        config_file = tmp_path / "config.yml"
        config_file.write_text(
            """base_package: com.test.app
ai_provider: claude-code
"""
        )

        profile = JpaMtProfile.from_config_file(config_file)

        assert profile.config.ai_provider == "claude-code"

    def test_ai_provider_with_invalid_key_raises_error(self):
        """ai_provider raises KeyError for unregistered provider key."""
        config = JpaMtConfig(ai_provider="nonexistent-provider")
        profile = JpaMtProfile(config=config)

        with pytest.raises(KeyError) as exc_info:
            _ = profile.ai_provider

        assert "nonexistent-provider" in str(exc_info.value)

    def test_ai_provider_rejects_manual_provider(self):
        """ai_provider raises ValueError for 'manual' - it can't generate content."""
        config = JpaMtConfig(ai_provider="manual")
        profile = JpaMtProfile(config=config)

        with pytest.raises(ValueError) as exc_info:
            _ = profile.ai_provider

        assert "manual" in str(exc_info.value)

    def test_ai_provider_can_be_used_for_generation(self):
        """Injected provider can validate and generate content."""
        from unittest.mock import MagicMock

        profile = JpaMtProfile()
        mock_provider = MagicMock()
        mock_provider.generate.return_value = MagicMock(
            files={"output.java": "public class Output {}"}
        )

        # Inject mock
        profile._ai_provider = mock_provider

        # Use provider for generation
        result = profile.ai_provider.generate("Generate a Java class")

        mock_provider.generate.assert_called_once_with("Generate a Java class")
        assert result.files["output.java"] == "public class Output {}"

    @pytest.mark.claude_code
    def test_ai_provider_with_claude_code_validates(self):
        """Claude Code provider can be validated when available.

        This is an integration test - requires claude CLI to be installed.
        Run with: pytest -m claude_code
        """
        config = JpaMtConfig(ai_provider="claude-code")
        profile = JpaMtProfile(config=config)

        provider = profile.ai_provider

        # Should not raise if claude CLI is available
        provider.validate()
        # Verify it conforms to interface
        assert hasattr(provider, "generate")
        assert callable(provider.generate)


class TestTemplateRendering:
    """Smoke tests for template rendering."""

    @pytest.fixture
    def profile(self):
        """Create a JpaMtProfile instance."""
        return JpaMtProfile()

    @pytest.fixture
    def minimal_context(self):
        """Minimal context for prompt generation."""
        return {
            "entity": "Customer",
            "table": "customers",
            "bounded_context": "crm",
            "scope": "domain",
        }

    def test_planning_prompt_renders_without_error(self, profile, minimal_context):
        """Planning prompt renders without crashing."""
        prompt = profile.generate_planning_prompt(minimal_context)

        # Basic validity checks
        assert isinstance(prompt, str)
        assert len(prompt) > 500  # Should be substantial
        assert "Customer" in prompt
        assert "customers" in prompt
        assert "## Role" in prompt
        assert "## Task" in prompt

    def test_generation_prompt_renders_without_error(self, profile, minimal_context):
        """Generation prompt renders without crashing."""
        prompt = profile.generate_generation_prompt(minimal_context)

        assert isinstance(prompt, str)
        assert len(prompt) > 200
        assert "Customer" in prompt

    def test_review_prompt_renders_without_error(self, profile, minimal_context):
        """Review prompt renders without crashing."""
        prompt = profile.generate_review_prompt(minimal_context)

        assert isinstance(prompt, str)
        assert len(prompt) > 200
        assert "Customer" in prompt

    def test_revision_prompt_renders_without_error(self, profile, minimal_context):
        """Revision prompt renders without crashing."""
        prompt = profile.generate_revision_prompt(minimal_context)

        assert isinstance(prompt, str)
        assert len(prompt) > 200
        assert "Customer" in prompt

    def test_all_scopes_render_planning_prompt(self, profile):
        """All scopes can generate planning prompts."""
        scopes = ["domain", "service", "api", "full"]

        for scope in scopes:
            context = {
                "entity": "TestEntity",
                "table": "test_entities",
                "bounded_context": "test",
                "scope": scope,
            }
            prompt = profile.generate_planning_prompt(context)
            assert isinstance(prompt, str), f"Failed for scope: {scope}"
            assert len(prompt) > 100, f"Prompt too short for scope: {scope}"

    def test_template_uses_yaml_config(self, profile, minimal_context):
        """Planning prompt uses YAML configuration."""
        prompt = profile.generate_planning_prompt(minimal_context)

        # These come from planning-prompt.yml
        assert "JPA Multi-Tenant" in prompt  # From role.title
        assert "Implementation Plan" in prompt  # From expected_output
        assert "Schema Analysis" in prompt  # From task phases

    def test_conventions_with_default_context(self, profile):
        """Templates work with no conventions specified."""
        context = {
            "entity": "Product",
            "table": "products",
            "bounded_context": "inventory",
            "scope": "domain",
            # No conventions specified
        }
        prompt = profile.generate_planning_prompt(context)

        # Should still render without errors
        assert isinstance(prompt, str)
        assert "Product" in prompt

    def test_template_has_no_unresolved_required_vars(self, profile, minimal_context):
        """Templates resolve required variables."""
        prompt = profile.generate_planning_prompt(minimal_context)

        # These context vars should be resolved
        assert "{{entity}}" not in prompt
        assert "{{table}}" not in prompt
        assert "{{bounded_context}}" not in prompt
        assert "{{scope}}" not in prompt

        # Engine vars like {{STANDARDS}} are expected to remain
        # (resolved by PromptAssembler, not profile)
