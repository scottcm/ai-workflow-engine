"""Tests for SessionStore utility methods.

Covers:
- exists() method (lines 96-97)
- list_sessions() method (lines 106-114)
- delete() method (lines 126-132)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from aiwf.domain.persistence.session_store import SessionStore
from aiwf.domain.models.workflow_state import (
    ExecutionMode,
    PhaseTransition,
    WorkflowPhase,
    WorkflowState,
    WorkflowStatus,
)


def _create_valid_session_json(session_id: str) -> dict:
    """Create a valid session.json data structure."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "session_id": session_id,
        "profile": "jpa-mt",
        "scope": "domain",
        "entity": "TestEntity",
        "providers": {"planner": "manual"},
        "execution_mode": "interactive",
        "phase": "initialized",
        "status": "in_progress",
        "current_iteration": 1,
        "standards_hash": "abc123",
        "phase_history": [{"phase": "initialized", "status": "in_progress"}],
        "created_at": now,
        "updated_at": now,
        "artifacts": [],
        "prompt_hashes": {},
    }


class TestSessionStoreExists:
    """Tests for SessionStore.exists() method."""

    def test_exists_returns_true_when_session_file_exists(self, tmp_path: Path) -> None:
        """exists() returns True when session.json file exists."""
        sessions_root = tmp_path / "sessions"
        store = SessionStore(sessions_root=sessions_root)

        session_id = "test-session-exists"
        session_dir = sessions_root / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        # Create valid session.json
        session_file = session_dir / "session.json"
        session_file.write_text(
            json.dumps(_create_valid_session_json(session_id)),
            encoding="utf-8",
        )

        assert store.exists(session_id) is True

    def test_exists_returns_false_when_session_missing(self, tmp_path: Path) -> None:
        """exists() returns False when session doesn't exist."""
        sessions_root = tmp_path / "sessions"
        store = SessionStore(sessions_root=sessions_root)

        assert store.exists("nonexistent-session") is False

    def test_exists_returns_false_when_dir_exists_but_no_session_json(
        self, tmp_path: Path
    ) -> None:
        """exists() returns False when directory exists but session.json is missing."""
        sessions_root = tmp_path / "sessions"
        store = SessionStore(sessions_root=sessions_root)

        session_id = "partial-session"
        session_dir = sessions_root / session_id
        session_dir.mkdir(parents=True, exist_ok=True)
        # Don't create session.json

        assert store.exists(session_id) is False


class TestSessionStoreListSessions:
    """Tests for SessionStore.list_sessions() method."""

    def test_list_sessions_returns_sorted_ids(self, tmp_path: Path) -> None:
        """list_sessions() returns session IDs sorted alphabetically."""
        sessions_root = tmp_path / "sessions"
        store = SessionStore(sessions_root=sessions_root)

        # Create sessions in non-alphabetical order
        session_ids = ["zebra-session", "alpha-session", "beta-session"]
        for session_id in session_ids:
            session_dir = sessions_root / session_id
            session_dir.mkdir(parents=True, exist_ok=True)
            session_file = session_dir / "session.json"
            session_file.write_text(
                json.dumps(_create_valid_session_json(session_id)),
                encoding="utf-8",
            )

        result = store.list_sessions()

        assert result == ["alpha-session", "beta-session", "zebra-session"]

    def test_list_sessions_empty_dir_returns_empty(self, tmp_path: Path) -> None:
        """list_sessions() returns empty list when no sessions exist."""
        sessions_root = tmp_path / "sessions"
        store = SessionStore(sessions_root=sessions_root)

        result = store.list_sessions()

        assert result == []

    def test_list_sessions_ignores_dirs_without_session_json(
        self, tmp_path: Path
    ) -> None:
        """list_sessions() ignores directories that don't contain session.json."""
        sessions_root = tmp_path / "sessions"
        store = SessionStore(sessions_root=sessions_root)

        # Create a valid session
        valid_session = "valid-session"
        valid_dir = sessions_root / valid_session
        valid_dir.mkdir(parents=True, exist_ok=True)
        (valid_dir / "session.json").write_text(
            json.dumps(_create_valid_session_json(valid_session)),
            encoding="utf-8",
        )

        # Create an invalid directory (no session.json)
        invalid_dir = sessions_root / "invalid-session"
        invalid_dir.mkdir(parents=True, exist_ok=True)
        # Don't create session.json

        result = store.list_sessions()

        assert result == ["valid-session"]

    def test_list_sessions_ignores_files_in_sessions_root(
        self, tmp_path: Path
    ) -> None:
        """list_sessions() ignores files (non-directories) in sessions root."""
        sessions_root = tmp_path / "sessions"
        store = SessionStore(sessions_root=sessions_root)

        # Create a valid session
        valid_session = "valid-session"
        valid_dir = sessions_root / valid_session
        valid_dir.mkdir(parents=True, exist_ok=True)
        (valid_dir / "session.json").write_text(
            json.dumps(_create_valid_session_json(valid_session)),
            encoding="utf-8",
        )

        # Create a file in sessions root (should be ignored)
        (sessions_root / "some-file.txt").write_text("not a session", encoding="utf-8")

        result = store.list_sessions()

        assert result == ["valid-session"]


class TestSessionStoreDelete:
    """Tests for SessionStore.delete() method."""

    def test_delete_removes_session_directory(self, tmp_path: Path) -> None:
        """delete() removes the entire session directory."""
        sessions_root = tmp_path / "sessions"
        store = SessionStore(sessions_root=sessions_root)

        session_id = "session-to-delete"
        session_dir = sessions_root / session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        # Create session.json and some additional files
        (session_dir / "session.json").write_text(
            json.dumps(_create_valid_session_json(session_id)),
            encoding="utf-8",
        )
        iteration_dir = session_dir / "iteration-1"
        iteration_dir.mkdir(parents=True, exist_ok=True)
        (iteration_dir / "planning-prompt.md").write_text("prompt", encoding="utf-8")

        # Verify session exists
        assert session_dir.exists()
        assert store.exists(session_id)

        # Delete
        store.delete(session_id)

        # Verify completely removed
        assert not session_dir.exists()
        assert not store.exists(session_id)

    def test_delete_missing_raises_filenotfounderror(self, tmp_path: Path) -> None:
        """delete() raises FileNotFoundError for non-existent session."""
        sessions_root = tmp_path / "sessions"
        store = SessionStore(sessions_root=sessions_root)

        with pytest.raises(FileNotFoundError) as exc_info:
            store.delete("nonexistent-session")

        assert "nonexistent-session" in str(exc_info.value)

    def test_delete_does_not_affect_other_sessions(self, tmp_path: Path) -> None:
        """delete() only removes the specified session, not others."""
        sessions_root = tmp_path / "sessions"
        store = SessionStore(sessions_root=sessions_root)

        # Create two sessions
        for session_id in ["session-a", "session-b"]:
            session_dir = sessions_root / session_id
            session_dir.mkdir(parents=True, exist_ok=True)
            (session_dir / "session.json").write_text(
                json.dumps(_create_valid_session_json(session_id)),
                encoding="utf-8",
            )

        # Delete one
        store.delete("session-a")

        # Verify only session-a is deleted
        assert not store.exists("session-a")
        assert store.exists("session-b")
