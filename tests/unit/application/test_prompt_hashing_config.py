import hashlib
from pathlib import Path
import pytest

from aiwf.application.approval_specs import ING_APPROVAL_SPECS
from aiwf.application.config_loader import load_config
from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.models.workflow_state import (
    ExecutionMode,
    PhaseTransition,
    WorkflowPhase,
    WorkflowState,
    WorkflowStatus,
)
from aiwf.domain.persistence.session_store import SessionStore


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _build_state(session_id: str, phase: WorkflowPhase, current_iteration: int, providers: dict[str, str]) -> WorkflowState:
    return WorkflowState(
        session_id=session_id,
        profile="test-profile",
        scope="test-scope",
        entity="TestEntity",
        providers=providers,
        execution_mode=ExecutionMode.INTERACTIVE,
        phase=phase,
        status=WorkflowStatus.IN_PROGRESS,
        current_iteration=current_iteration,
        standards_hash="test-hash",
        phase_history=[PhaseTransition(phase=phase, status=WorkflowStatus.IN_PROGRESS)],
    )


def test_config_defaults_hash_prompts_false(tmp_path: Path) -> None:
    # Load config with isolated roots (hermetic)
    cfg = load_config(project_root=tmp_path, user_home=tmp_path)

    # Contract: merged config includes hash_prompts=False by default
    assert "hash_prompts" in cfg
    assert cfg["hash_prompts"] is False


def test_approve_records_prompt_hash_when_enabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sessions_root = tmp_path / "sessions"
    store = SessionStore(sessions_root=sessions_root)
    orch = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    phase = WorkflowPhase.GENERATING
    iteration = 1
    spec = ING_APPROVAL_SPECS[phase]
    provider_role = spec.provider_role

    session_id = "sess-generating-prompt-hash"
    session_dir = sessions_root / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    providers = {provider_role: "manual"}  # manual is fine; hashing is independent
    state = _build_state(session_id=session_id, phase=phase, current_iteration=iteration, providers=providers)
    store.save(state)

    prompt_relpath = spec.prompt_relpath_template.format(N=iteration)
    prompt_path = session_dir / prompt_relpath
    prompt_path.parent.mkdir(parents=True, exist_ok=True)

    prompt_content = "prompt-hash-me\n"
    prompt_path.write_text(prompt_content, encoding="utf-8", newline="\n")

    # Ensure provider is not the focal point; manual returns None
    def fake_run_provider(provider_key: str, prompt: str) -> str | None:
        return None

    import aiwf.application.approval_handler as approval_handler_module
    monkeypatch.setattr(approval_handler_module, "run_provider", fake_run_provider, raising=True)

    # When hash_prompts=False: prompt_hashes must not be modified
    orch.approve(session_id=session_id, hash_prompts=False)
    reloaded = store.load(session_id)
    assert reloaded.prompt_hashes == {}

    # When hash_prompts=True: prompt_hashes must record SHA256(prompt content)
    orch.approve(session_id=session_id, hash_prompts=True)
    reloaded2 = store.load(session_id)

    assert prompt_relpath in reloaded2.prompt_hashes
    assert reloaded2.prompt_hashes[prompt_relpath] == _sha256_text(prompt_content)
