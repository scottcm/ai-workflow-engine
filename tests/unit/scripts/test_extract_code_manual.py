from __future__ import annotations

from pathlib import Path
import runpy
import sys
import pytest

def _write_generation_response(path: Path) -> None:
    # Minimal valid bundle for the JPA-MT extractor
    content = (
        "<<<FILE: Tier.java>>>\n"
        "    package com.example;\n"
        "    public class Tier {}\n"
        "<<<FILE: TierRepository.java>>>\n"
        "    package com.example;\n"
        "    public interface TierRepository {}\n"
    )
    path.write_text(content, encoding="utf-8")

def _write_malformed_response(path: Path) -> None:
    path.write_text("This has no markers.", encoding="utf-8")

def _write_bad_filename_response(path: Path) -> None:
    # Contains one valid file and one invalid file to test partial write prevention
    content = (
        "<<<FILE: Good.java>>>\n"
        "    package com.example;\n"
        "    public class Good {}\n"
        "<<<FILE: ../Bad.java>>>\n"
        "    package com.example;\n"
        "    public class Bad {}\n"
    )
    path.write_text(content, encoding="utf-8")

@pytest.fixture
def script_path(repo_root: Path) -> str:
    path = repo_root / "scripts" / "extract_code_manual.py"
    # Fail fast if script is missing
    assert path.exists(), f"Script not found: {path}"
    return str(path)

@pytest.mark.unit
def test_extract_code_manual_happy_path(
    monkeypatch: pytest.MonkeyPatch,
    sessions_root: Path,
    capsys: pytest.CaptureFixture[str],
    script_path: str,
) -> None:
    session_id = "test-session"
    iteration = 1
    iteration_dir = sessions_root / session_id / f"iteration-{iteration}"
    iteration_dir.mkdir(parents=True, exist_ok=True)
    
    _write_generation_response(iteration_dir / "generation-response.md")
    
    # Establish pre-existing session.json to test immutability
    session_json = sessions_root / session_id / "session.json"
    session_json.write_text("{}", encoding="utf-8")
    
    monkeypatch.setenv("AIWF_SESSIONS_ROOT", str(sessions_root))
    monkeypatch.setattr(sys, "argv", [
        "scripts/extract_code_manual.py",
        "--session-id", session_id,
        "--iteration", str(iteration),
    ])
    
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(script_path, run_name="__main__")
    assert exc.value.code == 0
    
    # Assert session.json is unchanged
    assert session_json.read_text(encoding="utf-8") == "{}"

    out = capsys.readouterr().out
    assert "Extracted 2 files:" in out
    # Check for indented output as per spec
    assert f"    iteration-{iteration}/code/Tier.java" in out
    assert f"    iteration-{iteration}/code/TierRepository.java" in out
    
    # Resilient assertion for "Written to:" (accepts absolute or relative)
    code_dir = iteration_dir / "code"
    assert (
        f"Written to: {code_dir}" in out or 
        f"Written to: iteration-{iteration}/code" in out
    )

@pytest.mark.unit
def test_extract_code_manual_missing_response(
    monkeypatch: pytest.MonkeyPatch,
    sessions_root: Path,
    script_path: str,
) -> None:
    session_id = "test-session-missing"
    iteration = 1
    iteration_dir = sessions_root / session_id / f"iteration-{iteration}"
    iteration_dir.mkdir(parents=True, exist_ok=True)
    
    # Do NOT create generation-response.md
    
    session_json = sessions_root / session_id / "session.json"
    session_json.write_text("{}", encoding="utf-8")
    
    monkeypatch.setenv("AIWF_SESSIONS_ROOT", str(sessions_root))
    monkeypatch.setattr(sys, "argv", [
        "scripts/extract_code_manual.py",
        "--session-id", session_id,
        "--iteration", str(iteration),
    ])
    
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(script_path, run_name="__main__")
    assert exc.value.code == 1
    
    # Assert session.json unchanged
    assert session_json.read_text(encoding="utf-8") == "{}"
    # Assert no files written
    code_dir = iteration_dir / "code"
    if code_dir.exists():
        assert not any(code_dir.iterdir())

@pytest.mark.unit
def test_extract_code_manual_profile_selection(
    monkeypatch: pytest.MonkeyPatch,
    sessions_root: Path,
    script_path: str,
) -> None:
    session_id = "test-session-profiles"
    iteration = 1
    iteration_dir = sessions_root / session_id / f"iteration-{iteration}"
    iteration_dir.mkdir(parents=True, exist_ok=True)
    
    _write_generation_response(iteration_dir / "generation-response.md")
    monkeypatch.setenv("AIWF_SESSIONS_ROOT", str(sessions_root))
    
    # Case 1: Invalid Profile -> Fail
    monkeypatch.setattr(sys, "argv", [
        "scripts/extract_code_manual.py",
        "--session-id", session_id,
        "--iteration", str(iteration),
        "--profile", "does-not-exist"
    ])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(script_path, run_name="__main__")
    assert exc.value.code == 1
    
    # Case 2: Explicit Valid Profile -> Success
    monkeypatch.setattr(sys, "argv", [
        "scripts/extract_code_manual.py",
        "--session-id", session_id,
        "--iteration", str(iteration),
        "--profile", "jpa-mt"
    ])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(script_path, run_name="__main__")
    assert exc.value.code == 0
    
    assert (iteration_dir / "code" / "Tier.java").exists()

@pytest.mark.unit
def test_extract_code_manual_malformed(
    monkeypatch: pytest.MonkeyPatch,
    sessions_root: Path,
    script_path: str,
) -> None:
    session_id = "test-session-malformed"
    iteration = 1
    iteration_dir = sessions_root / session_id / f"iteration-{iteration}"
    iteration_dir.mkdir(parents=True, exist_ok=True)
    
    _write_malformed_response(iteration_dir / "generation-response.md")
    
    session_json = sessions_root / session_id / "session.json"
    session_json.write_text("{}", encoding="utf-8")
    
    monkeypatch.setenv("AIWF_SESSIONS_ROOT", str(sessions_root))
    monkeypatch.setattr(sys, "argv", [
        "scripts/extract_code_manual.py",
        "--session-id", session_id,
        "--iteration", str(iteration),
    ])
    
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(script_path, run_name="__main__")
    assert exc.value.code == 1
    
    # Assert session.json unchanged
    assert session_json.read_text(encoding="utf-8") == "{}"
    # Assert no files written
    code_dir = iteration_dir / "code"
    if code_dir.exists():
        assert not any(code_dir.iterdir())

@pytest.mark.unit
def test_extract_code_manual_write_failure(
    monkeypatch: pytest.MonkeyPatch,
    sessions_root: Path,
    script_path: str,
) -> None:
    session_id = "test-session-write-fail"
    iteration = 1
    iteration_dir = sessions_root / session_id / f"iteration-{iteration}"
    iteration_dir.mkdir(parents=True, exist_ok=True)
    
    _write_bad_filename_response(iteration_dir / "generation-response.md")
    
    session_json = sessions_root / session_id / "session.json"
    session_json.write_text("{}", encoding="utf-8")
    
    monkeypatch.setenv("AIWF_SESSIONS_ROOT", str(sessions_root))
    monkeypatch.setattr(sys, "argv", [
        "scripts/extract_code_manual.py",
        "--session-id", session_id,
        "--iteration", str(iteration),
    ])
    
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(script_path, run_name="__main__")
    assert exc.value.code == 1
    
    # Assert session.json unchanged
    assert session_json.read_text(encoding="utf-8") == "{}"
    
    # Assert no files written (no partial writes)
    code_dir = iteration_dir / "code"
    # Even though "Good.java" was valid, it must not be written if the batch fails
    if code_dir.exists():
        assert not (code_dir / "Good.java").exists()
        assert not any(code_dir.iterdir())