import textwrap
import pytest
from pathlib import Path

from aiwf.domain.models.workflow_state import Artifact, WorkflowPhase
from aiwf.domain.generation_step import process_generation_response
from profiles.jpa_mt.jpa_mt_profile import JpaMtProfile
from profiles.jpa_mt.file_writer import write_files

@pytest.fixture
def jpa_profile(standards_samples_dir: Path, utf8: str):
    """
    Creates a real JpaMtProfile instance configured with the standards samples directory.
    This ensures parsing logic is tested against the real bundle extractor.
    """
    config = {
        "scopes": {
            "domain": {
                "layers": ["entity", "repository"]
            }
        },
        "layer_standards": {
            "_universal": [],
            "entity": [],
            "repository": []
        },
        "standards": {
            "root": str(standards_samples_dir)
        },
        "artifacts": {
            "target_root": "code"
        }
    }
    # Using **config to pass dict keys as keyword arguments to __init__
    return JpaMtProfile(**config)

def test_process_generation_response_happy_path(
    sessions_root: Path,
    jpa_profile: JpaMtProfile,
    utf8: str
):
    """
    Happy Path:
    - Valid bundle content with filename-only markers.
    - Extractor parses files.
    - Writer writes to {session_dir}/iteration-{n}/code/.
    - Returns list of Artifacts with paths relative to session_dir.
    """
    session_dir = sessions_root / "test-session"
    iteration = 1
    
    # Valid bundle content
    bundle_content = textwrap.dedent("""
        <<<FILE: Tier.java>>>
            package com.example;
            public class Tier {}
        <<<FILE: TierRepository.java>>>
            package com.example;
            public interface TierRepository {}
    """)
    
    artifacts = process_generation_response(
        bundle_content=bundle_content,
        session_dir=session_dir,
        iteration=iteration,
        extractor=jpa_profile.parse_bundle,
        writer=write_files,
    )
    
    # Assertions
    assert len(artifacts) == 2
    
    # Sort artifacts to ensure deterministic checks
    sorted_artifacts = sorted(artifacts, key=lambda a: a.file_path)
    
    # Check Tier.java artifact
    a1 = sorted_artifacts[0]
    assert a1.phase == WorkflowPhase.GENERATED
    assert a1.artifact_type == "code"
    assert a1.file_path == f"iteration-{iteration}/code/Tier.java"
    
    # Check TierRepository.java artifact
    a2 = sorted_artifacts[1]
    assert a2.phase == WorkflowPhase.GENERATED
    assert a2.artifact_type == "code"
    assert a2.file_path == f"iteration-{iteration}/code/TierRepository.java"
    
    # Check files on disk
    code_dir = session_dir / f"iteration-{iteration}" / "code"
    assert code_dir.exists()
    
    file1 = code_dir / "Tier.java"
    assert file1.exists()
    assert "public class Tier {}" in file1.read_text(encoding=utf8)
    
    file2 = code_dir / "TierRepository.java"
    assert file2.exists()
    assert "public interface TierRepository {}" in file2.read_text(encoding=utf8)

def test_process_generation_response_empty_bundle(
    sessions_root: Path,
    jpa_profile: JpaMtProfile
):
    """
    Error Case: Empty or whitespace-only bundle content.
    - Must raise ValueError.
    - Must not create code directory.
    """
    session_dir = sessions_root / "test-session"
    
    with pytest.raises(ValueError):
        process_generation_response(
            bundle_content="   \n   ",
            session_dir=session_dir,
            iteration=1,
            extractor=jpa_profile.parse_bundle,
            writer=write_files,
        )
    
    # Ensure no directory created
    code_dir = session_dir / "iteration-1" / "code"
    assert not code_dir.exists()

def test_process_generation_response_malformed_bundle(
    sessions_root: Path,
    jpa_profile: JpaMtProfile
):
    """
    Error Case: Malformed bundle (no markers).
    - Extractor raises ValueError.
    - Exception propagates.
    - No code directory created.
    """
    session_dir = sessions_root / "test-session"
    malformed_content = "This is not a valid bundle."
    
    with pytest.raises(ValueError):
        process_generation_response(
            bundle_content=malformed_content,
            session_dir=session_dir,
            iteration=1,
            extractor=jpa_profile.parse_bundle,
            writer=write_files,
        )
    
    # Ensure no directory created
    code_dir = session_dir / "iteration-1" / "code"
    assert not code_dir.exists()

def test_process_generation_response_write_failure(
    sessions_root: Path,
    jpa_profile: JpaMtProfile
):
    """
    Error Case: Write failure due to invalid filename in bundle.
    - Extractor parses successfully.
    - Writer raises ValueError (fail-fast validation).
    - Exception propagates.
    - No partial writes (relying on FileWriter implementation).
    """
    session_dir = sessions_root / "test-session"
    
    # Bundle with one valid and one invalid filename
    # Invalid filename triggers FileWriter validation error
    bundle_content = textwrap.dedent("""
        <<<FILE: Valid.java>>>
            package com.example;
            public class Valid {}
        <<<FILE: ../Invalid.java>>>
            package com.example;
            public class Invalid {}
    """)
    
    with pytest.raises(ValueError):
        process_generation_response(
            bundle_content=bundle_content,
            session_dir=session_dir,
            iteration=1,
            extractor=jpa_profile.parse_bundle,
            writer=write_files,
        )
    
    # Ensure nothing was written (fail-fast)
    code_dir = session_dir / "iteration-1" / "code"
    # FileWriter creates the dir before validation in some implementations, 
    # or might not if validation happens first. 
    # Checking if files exist is the critical part.
    if code_dir.exists():
        assert not any(code_dir.iterdir()), "Directory should be empty on write failure"
