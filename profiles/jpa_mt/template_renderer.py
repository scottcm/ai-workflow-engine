"""Template rendering utilities for JPA multi-tenant profile.

Integration Points:
-------------------
This class is designed for use by Phase 3 components:

1. ManualProvider (aiwf/infrastructure/ai/manual_provider.py)
   - Uses: renderer.render_template() to create prompt files
   - Writes: Rendered prompts to session directories

2. PromptWriter Service (aiwf/application/prompt_writer.py)
   - Uses: renderer.render_template() to generate prompts
   - Returns: Prompt content for writing to disk

3. Commands (aiwf/domain/commands/)
   - PreparePlanningCommand
   - PrepareGenerationCommand
   - PrepareReviewCommand
   - PrepareRevisionCommand
   - Each uses: renderer.render_template() for their phase

Architecture:
-------------
┌─────────────────────────────────────────────┐
│ Phase 3 Components                          │
│ (ManualProvider, Commands, Services)        │
└─────────────────┬───────────────────────────┘
                  │ uses
                  ↓
┌─────────────────────────────────────────────┐
│ TemplateRenderer                            │
│ - render_template()                         │
│ - _fill_placeholders()                      │
└─────────────────┬───────────────────────────┘
                  │ uses
                  ↓
┌─────────────────────────────────────────────┐
│ JpaMtProfile                                │
│ - prompt_template_for()                     │
│ - _resolve_template_includes()              │
└─────────────────────────────────────────────┘
"""

from pathlib import Path
from typing import Any
from aiwf.domain.models.workflow_state import WorkflowPhase
from .jpa_mt_profile import JpaMtProfile


class TemplateRenderer:
    """
    Handles template loading, composition, and placeholder filling.
    
    This class encapsulates the two-step process of rendering prompts:
    1. Resolve {{include: path}} directives to compose layered templates
    2. Fill {{PLACEHOLDER}} variables with actual values
    
    Usage:
        profile = JpaMtProfile(config)
        renderer = TemplateRenderer(profile)
        
        context = {
            "TASK_ID": "JIRA-123",
            "ENTITY": "Tier",
            "TABLE": "global.tiers",
            ...
        }
        
        prompt = renderer.render_template(
            WorkflowPhase.INITIALIZED,  # planning phase
            "domain",                    # scope
            context                      # placeholder values
        )
    """
    
    def __init__(self, profile: JpaMtProfile):
        """
        Initialize the renderer with a profile.
        
        Args:
            profile: The JpaMtProfile instance to use for template loading
        """
        self.profile = profile
    
    def render_template(
        self,
        phase: WorkflowPhase,
        scope: str,
        context: dict[str, Any]
    ) -> str:
        """
        Load template, resolve includes, and fill placeholders.
        
        This is the main entry point for template rendering. It:
        1. Gets the template path for the given phase and scope
        2. Resolves all {{include:}} directives recursively
        3. Fills all {{PLACEHOLDER}} variables with context values
        
        Args:
            phase: Workflow phase (INITIALIZED, PLANNED, GENERATED, REVIEWED)
            scope: Generation scope (domain, vertical)
            context: Values to fill placeholders with
                Required keys: TASK_ID, DEV, DATE, ENTITY, SCOPE, TABLE,
                              BOUNDED_CONTEXT, SESSION_ID, PROFILE, ITERATION
        
        Returns:
            Complete prompt ready to send to AI
        
        Raises:
            FileNotFoundError: If template or included file missing
            RuntimeError: If circular includes detected
            KeyError: If required context key missing
        
        Example:
            >>> context = {
            ...     "TASK_ID": "JIRA-123",
            ...     "DEV": "Scott",
            ...     "DATE": "2024-12-09",
            ...     "ENTITY": "Tier",
            ...     "SCOPE": "domain",
            ...     "TABLE": "global.tiers",
            ...     "BOUNDED_CONTEXT": "catalog",
            ...     "SESSION_ID": "session-001",
            ...     "PROFILE": "jpa-mt",
            ...     "ITERATION": "1"
            ... }
            >>> prompt = renderer.render_template(
            ...     WorkflowPhase.INITIALIZED, "domain", context
            ... )
            >>> "{{include:" in prompt
            False
            >>> "{{ENTITY}}" in prompt
            False
        """
        # Step 1: Get template path for this phase and scope
        template_path = self.profile.prompt_template_for(phase, scope)
        
        # Step 2: Resolve all {{include:}} directives
        template_content = self.profile._resolve_template_includes(template_path)
        
        # Step 3: Fill all {{PLACEHOLDER}} variables
        filled_content = self._fill_placeholders(template_content, context)
        
        return filled_content
    
    def _fill_placeholders(self, content: str, context: dict[str, Any]) -> str:
        """
        Replace {{PLACEHOLDER}} with context values.
        
        This method validates that all required placeholders are present
        in the context, then performs simple string replacement.
        
        Args:
            content: Template content with placeholders (includes already resolved)
            context: Dictionary of placeholder values
        
        Returns:
            Content with all placeholders filled
        
        Raises:
            KeyError: If required placeholder not in context
        
        Example:
            >>> content = "Entity: {{ENTITY}}, Table: {{TABLE}}"
            >>> context = {"ENTITY": "Tier", "TABLE": "global.tiers"}
            >>> result = renderer._fill_placeholders(content, context)
            >>> result
            'Entity: Tier, Table: global.tiers'
        """
        # Define required placeholders based on base.md metadata section
        required = {
            "TASK_ID",
            "DEV",
            "DATE",
            "ENTITY",
            "SCOPE",
            "TABLE",
            "BOUNDED_CONTEXT",
            "SESSION_ID",
            "PROFILE",
            "ITERATION",
        }
        
        # Verify all required keys present in context
        missing = required - set(context.keys())
        if missing:
            raise KeyError(
                f"Missing required context keys: {sorted(missing)}. "
                f"Required: {sorted(required)}"
            )
        
        # Replace each placeholder with its value
        result = content
        for key, value in context.items():
            placeholder = f"{{{{{key}}}}}"  # Construct {{KEY}}
            result = result.replace(placeholder, str(value))
        
        return result
