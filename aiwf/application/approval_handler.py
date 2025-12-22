import hashlib
from pathlib import Path

from aiwf.application.approval_specs import ED_APPROVAL_SPECS, ING_APPROVAL_SPECS
from aiwf.domain.models.workflow_state import Artifact, WorkflowPhase, WorkflowState, WorkflowStatus


# monkeypatch seam for provider invocation
def run_provider(provider_key: str, prompt: str) -> str | None:
    raise NotImplementedError("Provider execution is not implemented in scaffolding")


class ApprovalHandler:
    def approve(self, *, session_dir: Path, state: WorkflowState, hash_prompts: bool) -> WorkflowState:
        # ING Phases (Planning, Generating, Reviewing, Revising)
        if state.phase in ING_APPROVAL_SPECS:
            spec = ING_APPROVAL_SPECS[state.phase]
            provider_role = spec.provider_role

            if provider_role not in state.providers:
                raise ValueError(f"Provider not configured for role '{provider_role}'")

            provider_key = state.providers[provider_role]

            iteration = 1 if state.phase == WorkflowPhase.PLANNING else state.current_iteration
            prompt_relpath = spec.prompt_relpath_template.format(N=iteration)
            prompt_path = session_dir / prompt_relpath

            if not prompt_path.exists():
                raise FileNotFoundError(f"Cannot approve: missing prompt file '{prompt_relpath}' (expected at {prompt_path})")

            if hash_prompts:
                state.prompt_hashes[prompt_relpath] = hashlib.sha256(prompt_path.read_bytes()).hexdigest()

            prompt_content = prompt_path.read_text(encoding="utf-8")
            response = run_provider(provider_key, prompt_content)

            if response is not None:
                response_relpath = spec.response_relpath_template.format(N=iteration)
                response_path = session_dir / response_relpath
                response_path.parent.mkdir(parents=True, exist_ok=True)
                response_path.write_text(response, encoding="utf-8")

            return state

        # ED Phases (Planned, Generated, Revised, Reviewed)
        elif state.phase == WorkflowPhase.PLANNED:
            spec = ED_APPROVAL_SPECS.get(state.phase)
            if spec and spec.plan_relpath:
                plan_relpath = spec.plan_relpath
                plan_path = session_dir / plan_relpath
                if not plan_path.exists():
                    raise FileNotFoundError(f"Cannot approve: missing plan file '{plan_relpath}' (expected at {plan_path})")

                state.plan_approved = True
                state.plan_hash = hashlib.sha256(plan_path.read_bytes()).hexdigest()

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
