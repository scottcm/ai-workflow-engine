"""AI approval provider - delegates decision to a response provider.

ADR-0012 Phase 3: AI-powered approval for automated quality gates.
"""

import re
from typing import Any

from aiwf.domain.models.approval_result import ApprovalDecision, ApprovalResult
from aiwf.domain.models.workflow_state import WorkflowPhase, WorkflowStage
from aiwf.domain.providers.response_provider import ResponseProvider
from aiwf.domain.providers.approval_provider import ApprovalProvider


# Default prompt template for approval evaluation
_DEFAULT_APPROVAL_PROMPT = """You are an approval reviewer for a workflow phase.

## Task
Evaluate the following content and decide whether to APPROVE or REJECT it.

## Phase Context
- Phase: {phase}
- Stage: {stage}

## Content to Review
{files_content}

## Instructions
Respond with exactly one of:
- APPROVED (or APPROVED: optional comment)
- REJECTED: reason for rejection (required)

Your response must start with either APPROVED or REJECTED.
"""


class AIApprovalProvider(ApprovalProvider):
    """Approval provider that delegates decision to an AI.

    Uses a ResponseProvider to evaluate content and parse the response
    as an approval decision.
    """

    def __init__(
        self,
        response_provider: ResponseProvider,
        prompt_template: str | None = None,
    ) -> None:
        """Initialize with a response provider.

        Args:
            response_provider: The response provider to use for evaluation
            prompt_template: Optional custom prompt template
        """
        self._response_provider = response_provider
        self._template = prompt_template or _DEFAULT_APPROVAL_PROMPT

    def evaluate(
        self,
        *,
        phase: WorkflowPhase,
        stage: WorkflowStage,
        files: dict[str, str | None],
        context: dict[str, Any],
    ) -> ApprovalResult:
        """Evaluate content using response provider and return decision.

        Sends content to response provider and parses response as
        APPROVED or REJECTED with feedback.
        """
        prompt = self._build_prompt(phase, stage, files, context)
        response = self._response_provider.generate(prompt)

        return self._parse_response(response or "")

    @property
    def requires_user_input(self) -> bool:
        """AI provider does not require user input."""
        return False

    def _build_prompt(
        self,
        phase: WorkflowPhase,
        stage: WorkflowStage,
        files: dict[str, str | None],
        context: dict[str, Any],
    ) -> str:
        """Build the approval prompt from template and content."""
        # Format file contents
        files_content = self._format_files(files)

        return self._template.format(
            phase=phase.value,
            stage=stage.value,
            files_content=files_content,
        )

    def _format_files(self, files: dict[str, str | None]) -> str:
        """Format file contents for inclusion in prompt."""
        if not files:
            return "(no files)"

        parts = []
        for filename, content in files.items():
            if content is None:
                parts.append(f"### {filename}\n(file not found)")
            else:
                parts.append(f"### {filename}\n```\n{content}\n```")

        return "\n\n".join(parts)

    def _parse_response(self, response: str) -> ApprovalResult:
        """Parse AI response into ApprovalResult.

        Expected formats:
        - APPROVED
        - APPROVED: optional comment
        - REJECTED: required reason
        - approved (case insensitive)
        - rejected: reason (case insensitive)
        """
        if not response.strip():
            return ApprovalResult(
                decision=ApprovalDecision.REJECTED,
                feedback="AI returned empty response",
            )

        # Normalize and check for APPROVED/REJECTED prefix
        response_lower = response.strip().lower()

        # Check for APPROVED
        if response_lower.startswith("approved"):
            # Extract optional comment after colon
            match = re.match(r"approved\s*:?\s*(.*)", response, re.IGNORECASE)
            feedback = match.group(1).strip() if match else None
            return ApprovalResult(
                decision=ApprovalDecision.APPROVED,
                feedback=feedback if feedback else None,
            )

        # Check for REJECTED
        if response_lower.startswith("rejected"):
            # Extract required reason after colon
            match = re.match(r"rejected\s*:\s*(.*)", response, re.IGNORECASE | re.DOTALL)
            if match and match.group(1).strip():
                feedback = match.group(1).strip()
            else:
                feedback = "AI rejected without providing reason"
            return ApprovalResult(
                decision=ApprovalDecision.REJECTED,
                feedback=feedback,
            )

        # Ambiguous response - treat as rejection
        return ApprovalResult(
            decision=ApprovalDecision.REJECTED,
            feedback=f"Unclear AI response (expected APPROVED/REJECTED): {response[:100]}",
        )