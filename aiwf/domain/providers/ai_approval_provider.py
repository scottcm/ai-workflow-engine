"""AI-powered approval provider adapter.

ADR-0015: Wraps any ResponseProvider to function as an ApprovalProvider.
Uses standardized prompt templates per phase/stage.
"""

import logging
import re
from pathlib import Path
from typing import Any

from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStage
from aiwf.domain.models.approval_result import ApprovalResult, ApprovalDecision
from aiwf.domain.providers.approval_provider import ApprovalProvider
from aiwf.domain.providers.response_provider import ResponseProvider


logger = logging.getLogger(__name__)

# Size limits for file content in prompts (review feedback)
MAX_FILE_CONTENT_SIZE = 50_000  # 50KB per file
MAX_TOTAL_CONTENT_SIZE = 200_000  # 200KB total


# Approval prompt templates per phase/stage
APPROVAL_TEMPLATES: dict[tuple[str, str], str] = {
    ("plan", "response"): """Review the following plan for completeness and feasibility.

## Plan Content
{plan_content}

## Approval Criteria
{criteria}

## Instructions
**CRITICAL: You MUST respond with exactly the word "APPROVED" or "REJECTED" on the DECISION line.**
- Use "APPROVED" only if the plan meets all criteria
- Use "REJECTED" if any issues need to be addressed
- If REJECTED, provide specific, actionable feedback
{rewrite_instruction}

## Response Format (REQUIRED)
DECISION: APPROVED
or
DECISION: REJECTED
FEEDBACK: [Your feedback if rejected, or "None" if approved]
{suggested_format}
""",
    ("generate", "response"): """Verify the generated code implements the plan.

## Plan
{plan_content}

## Generated Code Files
{code_files}

## Question
Does this code implement what the plan specified? Check for:
- All planned features present
- No obvious implementation errors
- Files created as expected

**CRITICAL: You MUST respond with exactly the word "APPROVED" or "REJECTED" on the DECISION line.**

## Response Format (REQUIRED)
DECISION: APPROVED
or
DECISION: REJECTED
FEEDBACK: [Your feedback if rejected, or "None" if approved]
""",
    ("review", "response"): """Evaluate this code review for quality.

## Review Content
{review_content}

## Evaluation Criteria
- Is the review clear and specific?
- Are issues actionable (not vague)?
- Does it align with coding standards?

**CRITICAL: You MUST respond with exactly the word "APPROVED" or "REJECTED" on the DECISION line.**

## Response Format (REQUIRED)
DECISION: APPROVED
or
DECISION: REJECTED
FEEDBACK: [Your feedback if rejected, or "None" if approved]
""",
    ("revise", "response"): """Verify the revision addresses the agreed-upon issues.

## Issue Decisions
{issues_content}

## Revised Code
{code_files}

## Verification
- Were all ACCEPTED issues implemented?
- Are REJECTED issue explanations reasonable?
- Does the code compile/pass basic checks?

**CRITICAL: You MUST respond with exactly the word "APPROVED" or "REJECTED" on the DECISION line.**

## Response Format (REQUIRED)
DECISION: APPROVED
or
DECISION: REJECTED
FEEDBACK: [Your feedback if rejected, or "None" if approved]
""",
}

# Fallback template for stages without specific template
FALLBACK_TEMPLATE = """Evaluate the following content for approval.

## Content
{content}

**CRITICAL: You MUST respond with exactly the word "APPROVED" or "REJECTED" on the DECISION line.**

## Response Format (REQUIRED)
DECISION: APPROVED
or
DECISION: REJECTED
FEEDBACK: [Your feedback if rejected, or "None" if approved]
"""


class AIApprovalProvider(ApprovalProvider):
    """Wraps a ResponseProvider to function as an ApprovalProvider.

    Uses standardized prompt templates per phase/stage to get consistent
    approval decisions from any AI provider.
    """

    def __init__(self, response_provider: ResponseProvider):
        """Initialize with a response provider to wrap.

        Args:
            response_provider: The underlying provider to use for evaluation
        """
        self._provider = response_provider

    def evaluate(
        self,
        *,
        phase: WorkflowPhase,
        stage: WorkflowStage,
        files: dict[str, str | None],
        context: dict[str, Any],
    ) -> ApprovalResult:
        """Build approval prompt, call provider, parse response.

        Args:
            phase: Current workflow phase
            stage: Current stage
            files: Dict of filepath -> content
            context: Session metadata and criteria

        Returns:
            ApprovalResult with decision and feedback
        """
        prompt = self._build_prompt(phase, stage, files, context)

        result = self._provider.generate(prompt, context)
        if result is None:
            # Provider returned None (e.g., manual provider wrapped incorrectly)
            logger.warning("Wrapped provider returned None - rejecting")
            return ApprovalResult(
                decision=ApprovalDecision.REJECTED,
                feedback="Provider returned no response",
            )

        if result.response is None:
            # Provider returned ProviderResult with no response text
            # (e.g., file-only provider that writes but doesn't return text)
            logger.warning("Wrapped provider returned result with no response text - rejecting")
            return ApprovalResult(
                decision=ApprovalDecision.REJECTED,
                feedback="Provider returned no response text for approval evaluation",
            )

        return self._parse_response(result.response, context)

    def _build_prompt(
        self,
        phase: WorkflowPhase,
        stage: WorkflowStage,
        files: dict[str, str | None],
        context: dict[str, Any],
    ) -> str:
        """Build approval prompt from template."""
        template_key = (phase.value, stage.value)
        template = APPROVAL_TEMPLATES.get(template_key, FALLBACK_TEMPLATE)

        allow_rewrite = context.get("allow_rewrite", False)

        # Build substitution dict
        subs = {
            "plan_content": self._get_file_content(
                files, context, "plan_file", "plan.md"
            ),
            "code_files": self._format_code_files(files),
            "review_content": self._get_file_content(
                files, context, "review_file", "review-response.md"
            ),
            "issues_content": self._get_file_content(
                files, context, "revision_issues_file", "revision-issues.md"
            ),
            "criteria": self._load_criteria(context),
            "content": self._format_all_files(files),
            "rewrite_instruction": (
                "- You may suggest a rewrite if needed" if allow_rewrite else ""
            ),
            "suggested_format": (
                "SUGGESTED_CONTENT: [Your rewritten content if suggesting changes]"
                if allow_rewrite
                else ""
            ),
        }

        return template.format(**subs)

    def _get_file_content(
        self,
        files: dict[str, str | None],
        context: dict[str, Any],
        context_key: str,
        default_name: str,
    ) -> str:
        """Get file content from files dict or context path.

        Args:
            files: Dict of filepath -> content
            context: Context dict with file paths
            context_key: Key in context for file path
            default_name: Default filename suffix to match

        Returns:
            File content or placeholder message
        """
        # Try context-specified path first
        file_path = context.get(context_key)
        if file_path and file_path in files:
            content = files[file_path]
            if content is not None:
                return self._truncate_content(content, file_path)

        # Try default name pattern
        for path, content in files.items():
            if path.endswith(default_name) and content is not None:
                return self._truncate_content(content, path)

        return "[Content not available]"

    def _truncate_content(self, content: str, path: str) -> str:
        """Truncate content if it exceeds size limit."""
        if len(content) <= MAX_FILE_CONTENT_SIZE:
            return content

        truncated = content[:MAX_FILE_CONTENT_SIZE]
        logger.warning(
            f"File {path} truncated from {len(content)} to {MAX_FILE_CONTENT_SIZE} chars"
        )
        return truncated + f"\n\n[...truncated from {len(content)} chars]"

    def _load_criteria(self, context: dict[str, Any]) -> str:
        """Load criteria content from file path in context.

        Args:
            context: Context dict with optional criteria_file path

        Returns:
            Criteria content or default message
        """
        default_criteria = "Verify content is complete and correct."

        criteria_path = context.get("criteria_file")
        if not criteria_path:
            return default_criteria

        try:
            path = Path(criteria_path)
            if path.exists() and path.is_file():
                content = path.read_text(encoding="utf-8")
                return self._truncate_content(content, str(path))
            else:
                logger.warning(f"Criteria file not found: {criteria_path}")
                return default_criteria
        except Exception as e:
            logger.warning(f"Error loading criteria file {criteria_path}: {e}")
            return default_criteria

    def _format_code_files(self, files: dict[str, str | None]) -> str:
        """Format code files for inclusion in prompt.

        Excludes markdown files and applies size limits.
        """
        parts = []
        total_size = 0

        for path, content in files.items():
            # Skip non-code files
            if path.endswith((".md", "-prompt.md", "-response.md")):
                continue

            if content is not None:
                truncated = self._truncate_content(content, path)
                total_size += len(truncated)

                if total_size > MAX_TOTAL_CONTENT_SIZE:
                    parts.append(f"### {path}\n[Skipped - total size limit reached]")
                    continue

                parts.append(f"### {path}\n```\n{truncated}\n```")
            else:
                parts.append(f"### {path}\n[File exists but content not provided]")

        return "\n\n".join(parts) if parts else "[No code files]"

    def _format_all_files(self, files: dict[str, str | None]) -> str:
        """Format all files for inclusion in prompt."""
        parts = []
        total_size = 0

        for path, content in files.items():
            if content is not None:
                truncated = self._truncate_content(content, path)
                total_size += len(truncated)

                if total_size > MAX_TOTAL_CONTENT_SIZE:
                    parts.append(f"### {path}\n[Skipped - total size limit reached]")
                    continue

                parts.append(f"### {path}\n{truncated}")

        return "\n\n".join(parts) if parts else "[No files]"

    def _parse_response(
        self, response: str, context: dict[str, Any]
    ) -> ApprovalResult:
        """Parse AI response into ApprovalResult.

        Handles both well-formatted responses and fuzzy matching.
        """
        # Look for explicit DECISION line
        decision_match = re.search(
            r"DECISION:\s*(APPROVED|REJECTED)", response, re.IGNORECASE
        )

        if decision_match:
            decision = ApprovalDecision(decision_match.group(1).lower())
        else:
            # Fuzzy matching as fallback
            lower_response = response.lower()
            if "approved" in lower_response and "rejected" not in lower_response:
                decision = ApprovalDecision.APPROVED
            elif "rejected" in lower_response:
                decision = ApprovalDecision.REJECTED
            else:
                # Default to rejected if unclear (safer)
                logger.warning("Could not parse approval decision - defaulting to REJECTED")
                decision = ApprovalDecision.REJECTED

        # Extract feedback
        feedback = None
        feedback_match = re.search(
            r"FEEDBACK:\s*(.+?)(?=SUGGESTED_CONTENT:|$)", response, re.DOTALL | re.IGNORECASE
        )
        if feedback_match:
            feedback = feedback_match.group(1).strip()
            if feedback.lower() == "none":
                feedback = None

        # If rejected but no explicit feedback, use response as feedback or a default
        if decision == ApprovalDecision.REJECTED and not feedback:
            if response.strip():
                feedback = response[:500] if len(response) > 500 else response
            else:
                feedback = "Empty or invalid response from AI provider"

        # Extract suggested content if allow_rewrite
        suggested_content = None
        if context.get("allow_rewrite"):
            suggested_match = re.search(
                r"SUGGESTED_CONTENT:\s*(.+?)$", response, re.DOTALL | re.IGNORECASE
            )
            if suggested_match:
                suggested_content = suggested_match.group(1).strip()

        return ApprovalResult(
            decision=decision,
            feedback=feedback,
            suggested_content=suggested_content,
        )

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        """Return provider metadata."""
        return {
            "name": "ai-approval",
            "description": "AI-powered approval via ResponseProvider",
            "fs_ability": "varies",  # Depends on wrapped provider
        }
