import hashlib
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
import pytest

from aiwf.application.approval_specs import ING_APPROVAL_SPECS
from aiwf.application.workflow_orchestrator import WorkflowOrchestrator
from aiwf.domain.models.workflow_state import (
    ExecutionMode,
    PhaseTransition,
    WorkflowPhase,
    WorkflowState,
    WorkflowStatus,
)
from aiwf.domain.persistence.session_store import SessionStore


def _create_mock_provider() -> MagicMock:
    """Create a mock provider with default metadata for testing."""
    mock_provider = MagicMock()
    mock_provider.get_metadata.return_value = {
        "name": "mock-provider",
        "description": "Mock provider for testing",
        "requires_config": False,
        "config_keys": [],
        "default_connection_timeout": 10,
        "default_response_timeout": 60,
        "fs_ability": "none",
        "supports_system_prompt": False,
        "supports_file_attachments": False,
    }
    return mock_provider


@pytest.fixture(autouse=True)
def mock_provider_factory(monkeypatch: pytest.MonkeyPatch):
    """Mock ProviderFactory.create() to return a mock provider with default metadata."""
    mock_provider = _create_mock_provider()
    monkeypatch.setattr(
        "aiwf.domain.providers.provider_factory.ProviderFactory.create",
        lambda key: mock_provider,
    )
    yield mock_provider


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


def test_approve_generating_reads_prompt_calls_provider_writes_response(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sessions_root = tmp_path / "sessions"
    store = SessionStore(sessions_root=sessions_root)
    orch = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    phase = WorkflowPhase.GENERATING
    iteration = 1
    spec = ING_APPROVAL_SPECS[phase]
    provider_role = spec.provider_role

    session_id = "sess-generating-ing"
    session_dir = sessions_root / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    providers = {provider_role: "fake-llm"}
    state = _build_state(session_id=session_id, phase=phase, current_iteration=iteration, providers=providers)
    store.save(state)

    prompt_relpath = spec.prompt_relpath_template.format(N=iteration)
    response_relpath = spec.response_relpath_template.format(N=iteration)

    prompt_path = session_dir / prompt_relpath
    prompt_path.parent.mkdir(parents=True, exist_ok=True)

    # initial write
    prompt_path.write_text("v1\n", encoding="utf-8", newline="\n")
    # simulate user edit after initial write
    edited_prompt = "v2-edited\n"
    prompt_path.write_text(edited_prompt, encoding="utf-8", newline="\n")

    calls: dict[str, Any] = {}

    def fake_run_provider(provider_key: str, prompt: str, system_prompt: str | None = None) -> str | None:
        calls["provider_key"] = provider_key
        calls["prompt"] = prompt
        calls["system_prompt"] = system_prompt
        return "LLM response"

    import aiwf.application.approval_handler as approval_handler_module
    monkeypatch.setattr(approval_handler_module, "run_provider", fake_run_provider, raising=True)

    orch.approve(session_id=session_id, hash_prompts=False)

    reloaded = store.load(session_id)

    # provider called with assembled prompt (includes profile prompt)
    assert calls["provider_key"] == providers[provider_role]
    assert edited_prompt.strip() in calls["prompt"]  # Profile prompt is included in assembled prompt

    # response file written
    response_path = session_dir / response_relpath
    assert response_path.exists()
    assert response_path.read_text(encoding="utf-8") == "LLM response"

    # approve does NOT advance phase
    assert reloaded.phase == phase
    assert reloaded.status == WorkflowStatus.IN_PROGRESS


def test_approve_generating_manual_provider_no_response_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sessions_root = tmp_path / "sessions"
    store = SessionStore(sessions_root=sessions_root)
    orch = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    phase = WorkflowPhase.GENERATING
    iteration = 1
    spec = ING_APPROVAL_SPECS[phase]
    provider_role = spec.provider_role

    session_id = "sess-generating-manual"
    session_dir = sessions_root / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    providers = {provider_role: "manual"}
    state = _build_state(session_id=session_id, phase=phase, current_iteration=iteration, providers=providers)
    store.save(state)

    prompt_relpath = spec.prompt_relpath_template.format(N=iteration)
    response_relpath = spec.response_relpath_template.format(N=iteration)

    prompt_path = session_dir / prompt_relpath
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text("prompt\n", encoding="utf-8", newline="\n")

    called = {"count": 0}

    def fake_run_provider(provider_key: str, prompt: str, system_prompt: str | None = None) -> str | None:
        called["count"] += 1
        return None  # manual provider produces no response file

    import aiwf.application.approval_handler as approval_handler_module
    monkeypatch.setattr(approval_handler_module, "run_provider", fake_run_provider, raising=True)

    orch.approve(session_id=session_id, hash_prompts=False)

    reloaded = store.load(session_id)

    # provider invoked, but no response file written
    assert called["count"] == 1
    assert not (session_dir / response_relpath).exists()

    assert reloaded.status == WorkflowStatus.IN_PROGRESS
    assert reloaded.phase == phase


def test_approve_ing_missing_prompt_sets_error_status(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    sessions_root = tmp_path / "sessions"
    store = SessionStore(sessions_root=sessions_root)
    orch = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    phase = WorkflowPhase.GENERATING
    iteration = 1
    spec = ING_APPROVAL_SPECS[phase]
    provider_role = spec.provider_role

    session_id = "sess-generating-missing-prompt"
    session_dir = sessions_root / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    providers = {provider_role: "fake-llm"}
    state = _build_state(session_id=session_id, phase=phase, current_iteration=iteration, providers=providers)
    store.save(state)

    prompt_relpath = spec.prompt_relpath_template.format(N=iteration)
    response_relpath = spec.response_relpath_template.format(N=iteration)

    def fake_run_provider(provider_key: str, prompt: str) -> str | None:
        raise AssertionError("Provider must not be invoked when prompt file is missing")

    import aiwf.application.approval_handler as approval_handler_module
    monkeypatch.setattr(approval_handler_module, "run_provider", fake_run_provider, raising=True)

    state = orch.approve(session_id=session_id, hash_prompts=False)

    assert state.status == WorkflowStatus.ERROR
    assert state.last_error is not None

    normalized_err = state.last_error.replace("\\", "/").lower()

    # Must explain which prompt was expected and missing (path must be visible)
    assert prompt_relpath.lower() in normalized_err
    assert ("missing" in normalized_err) or ("not found" in normalized_err)

    # No response written
    assert not (session_dir / response_relpath).exists()


def test_approve_generating_with_existing_response_extracts_files_and_advances(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When generation-response.md exists, approve extracts code, writes files, creates artifacts, advances to GENERATED."""
    sessions_root = tmp_path / "sessions"
    store = SessionStore(sessions_root=sessions_root)
    orch = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    phase = WorkflowPhase.GENERATING
    iteration = 1
    spec = ING_APPROVAL_SPECS[phase]
    provider_role = spec.provider_role

    session_id = "sess-generating-existing-response"
    session_dir = sessions_root / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    providers = {provider_role: "fake-llm"}
    state = _build_state(session_id=session_id, phase=phase, current_iteration=iteration, providers=providers)
    state.profile = "jpa_mt"  # Use profile with bundle_extractor
    store.save(state)

    prompt_relpath = spec.prompt_relpath_template.format(N=iteration)
    response_relpath = spec.response_relpath_template.format(N=iteration)

    # Create iteration directory
    iteration_dir = session_dir / f"iteration-{iteration}"
    iteration_dir.mkdir(parents=True, exist_ok=True)

    # Create prompt file
    prompt_path = session_dir / prompt_relpath
    prompt_path.write_text("generation prompt\n", encoding="utf-8", newline="\n")

    # Create response file with FILE markers
    response_content = """
<<<FILE: Entity.java>>>
package com.example;

public class Entity {
    private Long id;
}

<<<FILE: EntityRepository.java>>>
package com.example;

public interface EntityRepository {
    Entity findById(Long id);
}
"""
    response_path = session_dir / response_relpath
    response_path.write_text(response_content, encoding="utf-8", newline="\n")

    # Provider should NOT be called since response already exists
    def fake_run_provider(provider_key: str, prompt: str) -> str | None:
        raise AssertionError("Provider must not be invoked when response file already exists")

    import aiwf.application.approval_handler as approval_handler_module
    monkeypatch.setattr(approval_handler_module, "run_provider", fake_run_provider, raising=True)

    result = orch.approve(session_id=session_id, hash_prompts=True)

    # Verify phase advanced to GENERATED
    assert result.phase == WorkflowPhase.GENERATED
    assert result.status == WorkflowStatus.IN_PROGRESS

    # Verify code files were written
    code_dir = iteration_dir / "code"
    assert code_dir.exists()
    assert (code_dir / "Entity.java").exists()
    assert (code_dir / "EntityRepository.java").exists()
    assert "public class Entity" in (code_dir / "Entity.java").read_text(encoding="utf-8")

    # Verify artifacts were created with hashes
    assert len(result.artifacts) == 2
    artifact_paths = {a.path for a in result.artifacts}
    assert "iteration-1/code/Entity.java" in artifact_paths
    assert "iteration-1/code/EntityRepository.java" in artifact_paths

    # Verify all artifacts have sha256 hashes
    for artifact in result.artifacts:
        assert artifact.sha256 is not None
        assert len(artifact.sha256) == 64  # SHA256 hex digest length
        assert artifact.phase == WorkflowPhase.GENERATED
        assert artifact.iteration == 1

    # Verify prompt was hashed
    assert prompt_relpath in result.prompt_hashes
    assert len(result.prompt_hashes[prompt_relpath]) == 64


def test_approve_reviewing_uses_reviewer_role_and_correct_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sessions_root = tmp_path / "sessions"
    store = SessionStore(sessions_root=sessions_root)
    orch = WorkflowOrchestrator(session_store=store, sessions_root=sessions_root)

    phase = WorkflowPhase.REVIEWING
    iteration = 1
    spec = ING_APPROVAL_SPECS[phase]
    provider_role = spec.provider_role

    session_id = "sess-reviewing-ing"
    session_dir = sessions_root / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    providers = {provider_role: "fake-reviewer"}
    state = _build_state(session_id=session_id, phase=phase, current_iteration=iteration, providers=providers)
    store.save(state)

    prompt_relpath = spec.prompt_relpath_template.format(N=iteration)
    response_relpath = spec.response_relpath_template.format(N=iteration)

    prompt_path = session_dir / prompt_relpath
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text("review prompt\n", encoding="utf-8", newline="\n")

    calls: dict[str, Any] = {}

    def fake_run_provider(provider_key: str, prompt: str, system_prompt: str | None = None) -> str | None:
        calls["provider_key"] = provider_key
        calls["prompt"] = prompt
        calls["system_prompt"] = system_prompt
        return "review response"

    import aiwf.application.approval_handler as approval_handler_module
    monkeypatch.setattr(approval_handler_module, "run_provider", fake_run_provider, raising=True)

    orch.approve(session_id=session_id, hash_prompts=False)

    assert calls["provider_key"] == providers[provider_role]
    assert "review prompt" in calls["prompt"]  # Profile prompt included in assembled prompt

    response_path = session_dir / response_relpath
    assert response_path.exists()
    assert response_path.read_text(encoding="utf-8") == "review response"

    reloaded = store.load(session_id)
    assert reloaded.phase == phase
