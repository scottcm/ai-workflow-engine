"""Tests for SessionStore error paths.

Covers:
- _deserialize with invalid data raises ValueError (line 160-161)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aiwf.domain.persistence.session_store import SessionStore


def test_session_store_deserialize_invalid_data_raises_valueerror(tmp_path: Path) -> None:
    """When session.json contains invalid data, load raises ValueError."""
    sessions_root = tmp_path / "sessions"
    store = SessionStore(sessions_root=sessions_root)

    session_id = "test-invalid-session"
    session_dir = sessions_root / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    # Write invalid session.json (missing required fields)
    session_file = session_dir / "session.json"
    invalid_data = {
        "session_id": session_id,
        "profile": "jpa-mt",
        # Missing required fields: scope, entity, providers, phase, status, standards_hash, etc.
    }
    session_file.write_text(json.dumps(invalid_data), encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        store.load(session_id)

    assert "Invalid session data" in str(exc_info.value)


def test_session_store_deserialize_malformed_json_raises(tmp_path: Path) -> None:
    """When session.json contains malformed JSON, load raises json.JSONDecodeError."""
    sessions_root = tmp_path / "sessions"
    store = SessionStore(sessions_root=sessions_root)

    session_id = "test-malformed-session"
    session_dir = sessions_root / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    # Write malformed JSON
    session_file = session_dir / "session.json"
    session_file.write_text("{ this is not valid json", encoding="utf-8")

    with pytest.raises(json.JSONDecodeError):
        store.load(session_id)


def test_session_store_deserialize_wrong_type_raises_valueerror(tmp_path: Path) -> None:
    """When session.json has wrong field types, load raises ValueError."""
    sessions_root = tmp_path / "sessions"
    store = SessionStore(sessions_root=sessions_root)

    session_id = "test-wrong-types"
    session_dir = sessions_root / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    # Write session.json with wrong types (phase should be enum, not int)
    session_file = session_dir / "session.json"
    invalid_data = {
        "session_id": session_id,
        "profile": "jpa-mt",
        "scope": "domain",
        "entity": "Test",
        "providers": {},
        "execution_mode": "interactive",
        "phase": 12345,  # Wrong type - should be string
        "status": "in_progress",
        "current_iteration": 1,
        "standards_hash": "abc123",
        "phase_history": [],
        "created_at": "2024-12-24T00:00:00",
        "updated_at": "2024-12-24T00:00:00",
    }
    session_file.write_text(json.dumps(invalid_data), encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        store.load(session_id)

    assert "Invalid session data" in str(exc_info.value)


def test_session_store_deserialize_invalid_phase_enum_raises_valueerror(tmp_path: Path) -> None:
    """When session.json has invalid phase enum value, load raises ValueError."""
    sessions_root = tmp_path / "sessions"
    store = SessionStore(sessions_root=sessions_root)

    session_id = "test-invalid-enum"
    session_dir = sessions_root / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    session_file = session_dir / "session.json"
    invalid_data = {
        "session_id": session_id,
        "profile": "jpa-mt",
        "scope": "domain",
        "entity": "Test",
        "providers": {},
        "execution_mode": "interactive",
        "phase": "NONEXISTENT_PHASE",  # Invalid enum value
        "status": "in_progress",
        "current_iteration": 1,
        "standards_hash": "abc123",
        "phase_history": [],
        "created_at": "2024-12-24T00:00:00",
        "updated_at": "2024-12-24T00:00:00",
    }
    session_file.write_text(json.dumps(invalid_data), encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        store.load(session_id)

    assert "Invalid session data" in str(exc_info.value)
