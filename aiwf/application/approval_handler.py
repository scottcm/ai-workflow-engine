import hashlib
import importlib
from abc import ABC, abstractmethod
from pathlib import Path

from aiwf.application.approval_specs import ED_APPROVAL_SPECS, ING_APPROVAL_SPECS
from aiwf.application.prompt_assembler import PromptAssembler
from aiwf.domain.models.workflow_state import Artifact, WorkflowPhase, WorkflowState, WorkflowStatus
from aiwf.domain.providers.capabilities import ProviderCapabilities  # noqa: F401 - re-export for compatibility


class ApprovalHandlerBase(ABC):
    """Base class for approval handlers in the Chain of Responsibility."""

    def __init__(self, successor: "ApprovalHandlerBase | None" = None) -> None:
        self._successor = successor

    @abstractmethod
    def can_handle(self, state: WorkflowState) -> bool:
        """Return True if this handler can process the given state."""
        ...

    @abstractmethod
    def handle(
        self, *, session_dir: Path, state: WorkflowState, hash_prompts: bool
    ) -> WorkflowState:
        """Process approval for the given state."""
        ...

    def approve(
        self, *, session_dir: Path, state: WorkflowState, hash_prompts: bool
    ) -> WorkflowState:
        """Chain method: handle if possible, otherwise delegate to successor."""
        if self.can_handle(state):
            return self.handle(
                session_dir=session_dir, state=state, hash_prompts=hash_prompts
            )
        if self._successor:
            return self._successor.approve(
                session_dir=session_dir, state=state, hash_prompts=hash_prompts
            )
        raise ValueError(f"No handler found for phase: {state.phase}")


def _compute_file_hash(path: Path) -> str:
    """Compute SHA256 hash of a file's contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_file_exists(path: Path, description: str, relpath: str) -> None:
    """Raise FileNotFoundError with standard message if path doesn't exist."""
    if not path.exists():
        raise FileNotFoundError(
            f"Cannot approve: missing {description} '{relpath}' (expected at {path})"
        )


def _hash_prompt_if_enabled(
    state: WorkflowState,
    prompt_path: Path,
    prompt_relpath: str,
    hash_prompts: bool,
) -> None:
    """Compute and store prompt hash if hashing is enabled and file exists."""
    if hash_prompts and prompt_path.exists():
        state.prompt_hashes[prompt_relpath] = _compute_file_hash(prompt_path)


def _update_or_create_artifact(
    state: WorkflowState,
    file_path: Path,
    session_dir: Path,
    phase: WorkflowPhase,
    iteration: int,
) -> None:
    """Update existing artifact's hash or create new artifact if not found."""
    relpath = file_path.relative_to(session_dir).as_posix()
    sha256 = _compute_file_hash(file_path)

    for artifact in state.artifacts:
        if artifact.path == relpath:
            artifact.sha256 = sha256
            return

    state.artifacts.append(Artifact(
        path=relpath,
        phase=phase,
        iteration=iteration,
        sha256=sha256,
    ))


def run_provider(
    provider_key: str,
    prompt: str,
    system_prompt: str | None = None,
) -> str | None:
    """Invoke an AI provider to generate a response.

    Args:
        provider_key: Registered provider key (e.g., "manual", "claude")
        prompt: The prompt text to send
        system_prompt: Optional system prompt for providers that support it

    Returns:
        Response string, or None if provider signals manual mode

    Raises:
        ProviderError: If provider fails (network, auth, timeout, etc.)
        KeyError: If provider_key is not registered
    """
    from aiwf.domain.providers.provider_factory import ProviderFactory

    provider = ProviderFactory.create(provider_key)
    metadata = provider.get_metadata()
    connection_timeout = metadata.get("default_connection_timeout")
    response_timeout = metadata.get("default_response_timeout")

    return provider.generate(
        prompt,
        system_prompt=system_prompt,
        connection_timeout=connection_timeout,
        response_timeout=response_timeout,
    )


def _extract_and_write_code_files(
    *,
    session_dir: Path,
    state: WorkflowState,
    response_content: str,
) -> None:
    """Extract code files from response using bundle_extractor and write to code directory.

    Creates Artifact records with computed hashes for each extracted file.
    """
    profile_module = state.profile.replace("-", "_")
    extractor_module = importlib.import_module(f"profiles.{profile_module}.bundle_extractor")

    if not hasattr(extractor_module, "extract_files"):
        raise ValueError(f"Profile '{state.profile}' does not have a bundle_extractor.extract_files function")

    files = extractor_module.extract_files(response_content)

    code_dir = session_dir / f"iteration-{state.current_iteration}" / "code"
    code_dir.mkdir(parents=True, exist_ok=True)

    for filename, file_content in files.items():
        file_path = code_dir / filename
        file_path.write_text(file_content, encoding="utf-8")

        relpath = file_path.relative_to(session_dir).as_posix()
        sha256 = _compute_file_hash(file_path)

        state.artifacts.append(Artifact(
            path=relpath,
            phase=WorkflowPhase.GENERATED,
            iteration=state.current_iteration,
            sha256=sha256,
        ))


class IngPhaseApprovalHandler(ApprovalHandlerBase):
    """Handles ING phases: PLANNING, GENERATING, REVIEWING, REVISING.

    Responsibility: Read prompt, call provider, write response.
    Special case: GENERATING with existing response extracts code and advances to GENERATED.
    """

    def can_handle(self, state: WorkflowState) -> bool:
        return state.phase in ING_APPROVAL_SPECS

    def handle(
        self, *, session_dir: Path, state: WorkflowState, hash_prompts: bool
    ) -> WorkflowState:
        # Special handling for GENERATING phase when response already exists
        if state.phase == WorkflowPhase.GENERATING:
            spec = ING_APPROVAL_SPECS[state.phase]
            response_relpath = spec.response_relpath_template.format(N=state.current_iteration)
            response_path = session_dir / response_relpath

            if response_path.exists():
                # Response exists - extract code, write files, create artifacts, advance to GENERATED
                prompt_relpath = spec.prompt_relpath_template.format(N=state.current_iteration)
                prompt_path = session_dir / prompt_relpath
                _hash_prompt_if_enabled(state, prompt_path, prompt_relpath, hash_prompts)

                response_content = response_path.read_text(encoding="utf-8")
                _extract_and_write_code_files(
                    session_dir=session_dir,
                    state=state,
                    response_content=response_content,
                )
                state.phase = WorkflowPhase.GENERATED
                return state

            # Response doesn't exist - fall through to standard ING phase handling

        # Standard ING phase handling
        spec = ING_APPROVAL_SPECS[state.phase]
        provider_role = spec.provider_role

        if provider_role not in state.providers:
            raise ValueError(f"Provider not configured for role '{provider_role}'")

        provider_key = state.providers[provider_role]

        prompt_relpath = spec.prompt_relpath_template.format(N=state.current_iteration)
        prompt_path = session_dir / prompt_relpath
        response_relpath = spec.response_relpath_template.format(N=state.current_iteration)

        _require_file_exists(prompt_path, "prompt file", prompt_relpath)
        _hash_prompt_if_enabled(state, prompt_path, prompt_relpath, hash_prompts)

        # Get provider capabilities
        from aiwf.domain.providers.provider_factory import ProviderFactory
        provider = ProviderFactory.create(provider_key)
        metadata = provider.get_metadata()
        fs_ability = metadata.get("fs_ability", "none")
        supports_system_prompt = metadata.get("supports_system_prompt", False)
        supports_file_attachments = metadata.get("supports_file_attachments", False)

        # Assemble prompt with session artifacts and output instructions
        profile_prompt = prompt_path.read_text(encoding="utf-8")
        assembler = PromptAssembler(session_dir, state)
        assembled = assembler.assemble(
            profile_prompt=profile_prompt,
            fs_ability=fs_ability,
            response_relpath=response_relpath,
            supports_system_prompt=supports_system_prompt,
            supports_file_attachments=supports_file_attachments,
        )

        response = run_provider(
            provider_key,
            assembled["user_prompt"],
            system_prompt=assembled["system_prompt"] or None,
        )

        if response is not None:
            response_path = session_dir / response_relpath
            response_path.parent.mkdir(parents=True, exist_ok=True)
            response_path.write_text(response, encoding="utf-8")

        return state


class PlannedApprovalHandler(ApprovalHandlerBase):
    """Handles PLANNED phase.

    Responsibility: Copy planning-response.md to plan.md, set plan_approved flag.
    """

    def can_handle(self, state: WorkflowState) -> bool:
        return state.phase == WorkflowPhase.PLANNED

    def handle(
        self, *, session_dir: Path, state: WorkflowState, hash_prompts: bool
    ) -> WorkflowState:
        ed_spec = ED_APPROVAL_SPECS.get(state.phase)
        ing_spec = ING_APPROVAL_SPECS.get(WorkflowPhase.PLANNING)

        if ed_spec and ed_spec.plan_relpath and ing_spec:
            # Read planning-response.md from iteration directory
            response_relpath = ing_spec.response_relpath_template.format(N=state.current_iteration)
            response_path = session_dir / response_relpath
            _require_file_exists(response_path, "planning response", response_relpath)

            # Write to plan.md in session root
            plan_relpath = ed_spec.plan_relpath
            plan_path = session_dir / plan_relpath
            plan_content = response_path.read_bytes()
            plan_path.write_bytes(plan_content)

            state.plan_approved = True
            state.plan_hash = hashlib.sha256(plan_content).hexdigest()

        return state


class CodeArtifactApprovalHandler(ApprovalHandlerBase):
    """Handles GENERATED and REVISED phases.

    Responsibility: Hash code files, create/update Artifact records.
    """

    def can_handle(self, state: WorkflowState) -> bool:
        return state.phase in {WorkflowPhase.GENERATED, WorkflowPhase.REVISED}

    def handle(
        self, *, session_dir: Path, state: WorkflowState, hash_prompts: bool
    ) -> WorkflowState:
        spec = ED_APPROVAL_SPECS.get(state.phase)

        if spec and spec.code_dir_relpath_template:
            code_dir_relpath = spec.code_dir_relpath_template.format(N=state.current_iteration)
            code_dir = session_dir / code_dir_relpath

            _require_file_exists(code_dir, "code directory", code_dir_relpath)

            # Recursively enumerate all files and update/create artifacts
            for file_path in code_dir.rglob("*"):
                if file_path.is_file():
                    _update_or_create_artifact(
                        state, file_path, session_dir, state.phase, state.current_iteration
                    )

        return state


class ReviewedApprovalHandler(ApprovalHandlerBase):
    """Handles REVIEWED phase.

    Responsibility: Hash review response, set review_approved flag.
    """

    def can_handle(self, state: WorkflowState) -> bool:
        return state.phase == WorkflowPhase.REVIEWED

    def handle(
        self, *, session_dir: Path, state: WorkflowState, hash_prompts: bool
    ) -> WorkflowState:
        spec = ED_APPROVAL_SPECS[WorkflowPhase.REVIEWED]
        # Assumes spec.response_relpath_template is set per constraints
        relpath = spec.response_relpath_template.format(N=state.current_iteration)
        response_path = session_dir / relpath

        _require_file_exists(response_path, "review response", relpath)

        state.review_hash = _compute_file_hash(response_path)
        state.review_approved = True

        return state


def build_approval_chain() -> ApprovalHandlerBase:
    """Build the standard approval handler chain.

    Chain order: ING phases first (most common), then ED phases.
    """
    reviewed = ReviewedApprovalHandler()
    code_artifact = CodeArtifactApprovalHandler(successor=reviewed)
    planned = PlannedApprovalHandler(successor=code_artifact)
    ing = IngPhaseApprovalHandler(successor=planned)
    return ing
