"""Fake response provider that returns configurable deterministic responses.

Used for integration testing to simulate AI responses without making actual API calls.
"""

from typing import Any, Callable

from aiwf.domain.providers.response_provider import ResponseProvider
from aiwf.domain.models.workflow_state import WorkflowPhase


# Type for response generators
ResponseGenerator = Callable[[str, dict[str, Any] | None], str]


class FakeResponseProvider(ResponseProvider):
    """Configurable fake provider for integration testing.

    Unlike ManualProvider (which returns None), this provider returns
    deterministic responses that can be configured per-phase or with
    custom generators.

    Usage:
        # Simple: same response for all prompts
        provider = FakeResponseProvider("# Response content")

        # Per-phase responses
        provider = FakeResponseProvider(
            phase_responses={
                WorkflowPhase.PLAN: "# Planning response...",
                WorkflowPhase.GENERATE: "```java\\npublic class Foo {}\\n```",
                WorkflowPhase.REVIEW: "@@@REVIEW_META\\nverdict: PASS\\n@@@",
            }
        )

        # Custom generator for dynamic responses
        def my_generator(prompt: str, context: dict | None) -> str:
            return f"Response to: {prompt[:50]}..."
        provider = FakeResponseProvider(generator=my_generator)
    """

    # Reasonable defaults for testing
    DEFAULT_PLAN_RESPONSE = """# Implementation Plan

## Overview
This is a mock planning response for integration testing.

## Steps
1. Step one
2. Step two
3. Step three
"""

    DEFAULT_GENERATE_RESPONSE = """# Generated Code

Here is the generated code:

```java
package com.example;

public class MockEntity {
    private Long id;

    public Long getId() { return id; }
    public void setId(Long id) { this.id = id; }
}
```
"""

    DEFAULT_REVIEW_RESPONSE_PASS = """# Code Review

## Summary
The code meets all requirements.

@@@REVIEW_META
verdict: PASS
@@@
"""

    DEFAULT_REVIEW_RESPONSE_FAIL = """# Code Review

## Summary
The code needs revisions.

## Issues
1. Missing validation

@@@REVIEW_META
verdict: FAIL
@@@
"""

    DEFAULT_REVISE_RESPONSE = """# Revised Code

Here is the revised code with fixes:

```java
package com.example;

public class MockEntity {
    private Long id;

    public Long getId() { return id; }
    public void setId(Long id) {
        if (id == null) throw new IllegalArgumentException("id required");
        this.id = id;
    }
}
```
"""

    def __init__(
        self,
        default_response: str | None = None,
        *,
        phase_responses: dict[WorkflowPhase, str] | None = None,
        generator: ResponseGenerator | None = None,
        review_verdict: str = "PASS",  # "PASS" or "FAIL"
    ):
        """Initialize the fake provider.

        Args:
            default_response: Response to return for all prompts (lowest priority)
            phase_responses: Dict mapping phase to response (medium priority)
            generator: Custom function to generate responses (highest priority)
            review_verdict: Default review verdict if using defaults ("PASS" or "FAIL")
        """
        self._default_response = default_response
        self._phase_responses = phase_responses or {}
        self._generator = generator
        self._review_verdict = review_verdict

        # Build default phase responses
        self._defaults = {
            WorkflowPhase.PLAN: self.DEFAULT_PLAN_RESPONSE,
            WorkflowPhase.GENERATE: self.DEFAULT_GENERATE_RESPONSE,
            WorkflowPhase.REVIEW: (
                self.DEFAULT_REVIEW_RESPONSE_PASS
                if review_verdict == "PASS"
                else self.DEFAULT_REVIEW_RESPONSE_FAIL
            ),
            WorkflowPhase.REVISE: self.DEFAULT_REVISE_RESPONSE,
        }

        # Track calls for assertions
        self.call_history: list[tuple[str, dict[str, Any] | None]] = []

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        return {
            "name": "fake-response",
            "description": "Fake provider returning configurable responses (testing)",
            "requires_config": False,
            "config_keys": [],
            "default_connection_timeout": None,
            "default_response_timeout": None,
            "fs_ability": "local-write",
            "supports_system_prompt": True,
            "supports_file_attachments": False,
        }

    def validate(self) -> None:
        """Always valid for testing."""
        pass

    def generate(
        self,
        prompt: str,
        context: dict[str, Any] | None = None,
        system_prompt: str | None = None,
        connection_timeout: int | None = None,
        response_timeout: int | None = None,
    ) -> str:
        """Generate a fake response.

        Priority order:
        1. Custom generator function
        2. Phase-specific response from phase_responses
        3. Default response if provided
        4. Built-in defaults based on detected phase
        """
        self.call_history.append((prompt, context))

        # Priority 1: Custom generator
        if self._generator is not None:
            return self._generator(prompt, context)

        # Detect phase from prompt filename patterns
        detected_phase = self._detect_phase(prompt)

        # Priority 2: Explicit phase response
        if detected_phase and detected_phase in self._phase_responses:
            return self._phase_responses[detected_phase]

        # Priority 3: Default response
        if self._default_response is not None:
            return self._default_response

        # Priority 4: Built-in defaults
        if detected_phase and detected_phase in self._defaults:
            return self._defaults[detected_phase]

        # Fallback
        return "# Mock Response\n\nThis is a fallback mock response."

    def _detect_phase(self, prompt: str) -> WorkflowPhase | None:
        """Detect workflow phase from prompt content.

        Looks for response filename hints in the prompt.
        """
        prompt_lower = prompt.lower()

        if "planning-response" in prompt_lower:
            return WorkflowPhase.PLAN
        elif "generation-response" in prompt_lower:
            return WorkflowPhase.GENERATE
        elif "review-response" in prompt_lower:
            return WorkflowPhase.REVIEW
        elif "revision-response" in prompt_lower:
            return WorkflowPhase.REVISE

        return None

    def reset_history(self) -> None:
        """Clear call history."""
        self.call_history.clear()