import hashlib
import importlib
from pathlib import Path

from aiwf.application.approval_specs import ED_APPROVAL_SPECS, ING_APPROVAL_SPECS
from aiwf.domain.models.workflow_state import Artifact, WorkflowPhase, WorkflowState, WorkflowStatus


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
        sha256 = hashlib.sha256(file_path.read_bytes()).hexdigest()

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
                if hash_prompts:
                    prompt_path = session_dir / prompt_relpath
                    if prompt_path.exists():
                        state.prompt_hashes[prompt_relpath] = hashlib.sha256(prompt_path.read_bytes()).hexdigest()

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

            if not prompt_path.exists():
                raise FileNotFoundError(f"Cannot approve: missing prompt file '{prompt_relpath}' (expected at {prompt_path})")

            if hash_prompts:
                state.prompt_hashes[prompt_relpath] = hashlib.sha256(prompt_path.read_bytes()).hexdigest()

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
                if not response_path.exists():
                    raise FileNotFoundError(f"Cannot approve: missing planning response '{response_relpath}' (expected at {response_path})")

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
            expected_path = session_dir / relpath

            if not expected_path.exists():
                raise FileNotFoundError(
                    f"Cannot approve: missing review response '{relpath}' (expected at {expected_path})"
                )

            state.review_hash = hashlib.sha256(expected_path.read_bytes()).hexdigest()
            state.review_approved = True

        elif state.phase in {WorkflowPhase.GENERATED, WorkflowPhase.REVISED}:
            spec = ED_APPROVAL_SPECS.get(state.phase)
            if spec and spec.code_dir_relpath_template:
                code_dir_relpath = spec.code_dir_relpath_template.format(N=state.current_iteration)
                code_dir = session_dir / code_dir_relpath
                
                if not code_dir.exists():
                    raise FileNotFoundError(f"Cannot approve: missing code directory '{code_dir_relpath}' (expected at {code_dir})")

                # Recursively enumerate all files
                for file_path in code_dir.rglob('*'):
                        if file_path.is_file():
                            relpath = file_path.relative_to(session_dir).as_posix()
                            sha256 = hashlib.sha256(file_path.read_bytes()).hexdigest()
                            
                            # Check if artifact exists
                            found = False
                            for artifact in state.artifacts:
                                if artifact.path == relpath:
                                    artifact.sha256 = sha256
                                    found = True
                                    break
                            
                            if not found:
                                state.artifacts.append(Artifact(
                                    path=relpath,
                                    phase=state.phase,
                                    iteration=state.current_iteration,
                                    sha256=sha256
                                ))
        
        return state
