"""Session file gateway for centralized file I/O.

Phase 6 of orchestrator modularization: centralize file I/O.
Provides a clean interface for reading/writing session files
without exposing Path operations to callers.
"""

from pathlib import Path
from typing import ClassVar

from aiwf.domain.models.workflow_state import WorkflowPhase


class SessionFileGateway:
    """Gateway for session file I/O operations.

    Centralizes file naming conventions and I/O operations.
    Callers work with phase/iteration semantics, not raw paths.
    """

    # Phase-to-filename mapping (single source of truth)
    PHASE_FILES: ClassVar[dict[WorkflowPhase, tuple[str, str]]] = {
        WorkflowPhase.PLAN: ("planning-prompt.md", "planning-response.md"),
        WorkflowPhase.GENERATE: ("generation-prompt.md", "generation-response.md"),
        WorkflowPhase.REVIEW: ("review-prompt.md", "review-response.md"),
        WorkflowPhase.REVISE: ("revision-prompt.md", "revision-response.md"),
    }

    def __init__(self, session_dir: Path) -> None:
        """Initialize gateway with session directory.

        Args:
            session_dir: Root directory for this session
        """
        self._session_dir = session_dir

    @property
    def session_dir(self) -> Path:
        """Get the session directory path."""
        return self._session_dir

    # ========================================================================
    # Directory Operations
    # ========================================================================

    def ensure_session_dir(self) -> Path:
        """Ensure session directory exists.

        Returns:
            Path to session directory
        """
        self._session_dir.mkdir(parents=True, exist_ok=True)
        return self._session_dir

    def ensure_iteration_dir(self, iteration: int) -> Path:
        """Ensure iteration directory exists.

        Args:
            iteration: Iteration number

        Returns:
            Path to iteration directory
        """
        iteration_dir = self._session_dir / f"iteration-{iteration}"
        iteration_dir.mkdir(parents=True, exist_ok=True)
        return iteration_dir

    def get_iteration_dir(self, iteration: int) -> Path:
        """Get iteration directory path (does not create).

        Args:
            iteration: Iteration number

        Returns:
            Path to iteration directory
        """
        return self._session_dir / f"iteration-{iteration}"

    def ensure_code_dir(self, iteration: int) -> Path:
        """Ensure code directory exists within iteration.

        Args:
            iteration: Iteration number

        Returns:
            Path to code directory
        """
        code_dir = self.get_iteration_dir(iteration) / "code"
        code_dir.mkdir(parents=True, exist_ok=True)
        return code_dir

    # ========================================================================
    # Prompt Operations
    # ========================================================================

    def get_prompt_filename(self, phase: WorkflowPhase) -> str:
        """Get prompt filename for phase.

        Args:
            phase: Workflow phase

        Returns:
            Prompt filename
        """
        return self.PHASE_FILES[phase][0]

    def get_response_filename(self, phase: WorkflowPhase) -> str:
        """Get response filename for phase.

        Args:
            phase: Workflow phase

        Returns:
            Response filename
        """
        return self.PHASE_FILES[phase][1]

    def get_prompt_path(self, iteration: int, phase: WorkflowPhase) -> Path:
        """Get full path to prompt file.

        Args:
            iteration: Iteration number
            phase: Workflow phase

        Returns:
            Path to prompt file
        """
        return self.get_iteration_dir(iteration) / self.get_prompt_filename(phase)

    def get_response_path(self, iteration: int, phase: WorkflowPhase) -> Path:
        """Get full path to response file.

        Args:
            iteration: Iteration number
            phase: Workflow phase

        Returns:
            Path to response file
        """
        return self.get_iteration_dir(iteration) / self.get_response_filename(phase)

    def prompt_exists(self, iteration: int, phase: WorkflowPhase) -> bool:
        """Check if prompt file exists.

        Args:
            iteration: Iteration number
            phase: Workflow phase

        Returns:
            True if prompt file exists
        """
        return self.get_prompt_path(iteration, phase).exists()

    def response_exists(self, iteration: int, phase: WorkflowPhase) -> bool:
        """Check if response file exists.

        Args:
            iteration: Iteration number
            phase: Workflow phase

        Returns:
            True if response file exists
        """
        return self.get_response_path(iteration, phase).exists()

    def read_prompt(self, iteration: int, phase: WorkflowPhase) -> str:
        """Read prompt file content.

        Args:
            iteration: Iteration number
            phase: Workflow phase

        Returns:
            Prompt file content

        Raises:
            FileNotFoundError: If prompt file doesn't exist
        """
        path = self.get_prompt_path(iteration, phase)
        if not path.exists():
            raise FileNotFoundError(f"Prompt file not found: {path}")
        return path.read_text(encoding="utf-8")

    def read_response(self, iteration: int, phase: WorkflowPhase) -> str:
        """Read response file content.

        Args:
            iteration: Iteration number
            phase: Workflow phase

        Returns:
            Response file content

        Raises:
            FileNotFoundError: If response file doesn't exist
        """
        path = self.get_response_path(iteration, phase)
        if not path.exists():
            raise FileNotFoundError(f"Response file not found: {path}")
        return path.read_text(encoding="utf-8")

    def write_prompt(
        self,
        iteration: int,
        phase: WorkflowPhase,
        content: str,
    ) -> Path:
        """Write prompt file.

        Creates iteration directory if needed.

        Args:
            iteration: Iteration number
            phase: Workflow phase
            content: Prompt content

        Returns:
            Path to written file
        """
        self.ensure_iteration_dir(iteration)
        path = self.get_prompt_path(iteration, phase)
        path.write_text(content, encoding="utf-8")
        return path

    def write_response(
        self,
        iteration: int,
        phase: WorkflowPhase,
        content: str,
    ) -> Path:
        """Write response file.

        Creates iteration directory if needed.

        Args:
            iteration: Iteration number
            phase: Workflow phase
            content: Response content

        Returns:
            Path to written file
        """
        self.ensure_iteration_dir(iteration)
        path = self.get_response_path(iteration, phase)
        path.write_text(content, encoding="utf-8")
        return path

    # ========================================================================
    # Code File Operations
    # ========================================================================

    def write_code_file(
        self,
        iteration: int,
        relative_path: str,
        content: str,
    ) -> Path:
        """Write a code file to the code directory.

        Creates code directory and parent directories if needed.

        Args:
            iteration: Iteration number
            relative_path: Path relative to code directory
            content: File content

        Returns:
            Path to written file
        """
        code_dir = self.ensure_code_dir(iteration)
        file_path = code_dir / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return file_path

    def read_code_files(self, iteration: int) -> dict[str, str]:
        """Read all code files from code directory.

        Args:
            iteration: Iteration number

        Returns:
            Dict mapping relative paths to content
        """
        code_dir = self.get_iteration_dir(iteration) / "code"
        files: dict[str, str] = {}

        if code_dir.exists():
            for file_path in code_dir.rglob("*"):
                if file_path.is_file():
                    rel_path = str(file_path.relative_to(code_dir))
                    files[rel_path] = file_path.read_text(encoding="utf-8")

        return files

    # ========================================================================
    # Plan File Operations
    # ========================================================================

    def get_plan_path(self) -> Path:
        """Get path to session-level plan file.

        Returns:
            Path to plan.md
        """
        return self._session_dir / "plan.md"

    def plan_exists(self) -> bool:
        """Check if plan file exists.

        Returns:
            True if plan.md exists
        """
        return self.get_plan_path().exists()

    def read_plan(self) -> str:
        """Read plan file content.

        Returns:
            Plan file content

        Raises:
            FileNotFoundError: If plan file doesn't exist
        """
        path = self.get_plan_path()
        if not path.exists():
            raise FileNotFoundError(f"Plan file not found: {path}")
        return path.read_text(encoding="utf-8")

    # ========================================================================
    # Generic File Operations (for approval context building)
    # ========================================================================

    def read_file(self, path: Path) -> str | None:
        """Read file content if it exists.

        Args:
            path: Absolute path to file

        Returns:
            File content, or None if file doesn't exist
        """
        if path.exists():
            return path.read_text(encoding="utf-8")
        return None

    def file_exists(self, path: Path) -> bool:
        """Check if file exists.

        Args:
            path: Absolute path to file

        Returns:
            True if file exists
        """
        return path.exists()