import hashlib
import importlib
from pathlib import Path

from aiwf.application.approval_specs import ED_APPROVAL_SPECS, ING_APPROVAL_SPECS
from aiwf.domain.models.workflow_state import Artifact, WorkflowPhase, WorkflowState, WorkflowStatus


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


# monkeypatch seam for provider invocation
def run_provider(provider_key: str, prompt: str) -> str | None:
    raise NotImplementedError("Provider execution is not implemented in scaffolding")


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


class ApprovalHandler:
    def approve(self, *, session_dir: Path, state: WorkflowState, hash_prompts: bool) -> WorkflowState:
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

        # ING Phases (Planning, Generating, Reviewing, Revising)
        if state.phase in ING_APPROVAL_SPECS:
            spec = ING_APPROVAL_SPECS[state.phase]
            provider_role = spec.provider_role

            if provider_role not in state.providers:
                raise ValueError(f"Provider not configured for role '{provider_role}'")

            provider_key = state.providers[provider_role]

            prompt_relpath = spec.prompt_relpath_template.format(N=state.current_iteration)
            prompt_path = session_dir / prompt_relpath

            _require_file_exists(prompt_path, "prompt file", prompt_relpath)
            _hash_prompt_if_enabled(state, prompt_path, prompt_relpath, hash_prompts)

            prompt_content = prompt_path.read_text(encoding="utf-8")
            response = run_provider(provider_key, prompt_content)

            if response is not None:
                response_relpath = spec.response_relpath_template.format(N=state.current_iteration)
                response_path = session_dir / response_relpath
                response_path.parent.mkdir(parents=True, exist_ok=True)
                response_path.write_text(response, encoding="utf-8")

            return state

        # ED Phases (Planned, Generated, Revised, Reviewed)
        elif state.phase == WorkflowPhase.PLANNED:
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

        elif state.phase == WorkflowPhase.REVIEWED:
            spec = ED_APPROVAL_SPECS[WorkflowPhase.REVIEWED]
            # Assumes spec.response_relpath_template is set per constraints
            relpath = spec.response_relpath_template.format(N=state.current_iteration)
            response_path = session_dir / relpath

            _require_file_exists(response_path, "review response", relpath)

            state.review_hash = _compute_file_hash(response_path)
            state.review_approved = True

        elif state.phase in {WorkflowPhase.GENERATED, WorkflowPhase.REVISED}:
            spec = ED_APPROVAL_SPECS.get(state.phase)
            if spec and spec.code_dir_relpath_template:
                code_dir_relpath = spec.code_dir_relpath_template.format(N=state.current_iteration)
                code_dir = session_dir / code_dir_relpath

                _require_file_exists(code_dir, "code directory", code_dir_relpath)

                # Recursively enumerate all files and update/create artifacts
                for file_path in code_dir.rglob('*'):
                    if file_path.is_file():
                        _update_or_create_artifact(
                            state, file_path, session_dir, state.phase, state.current_iteration
                        )
        
        return state
