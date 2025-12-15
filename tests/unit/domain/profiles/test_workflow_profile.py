import inspect
import pytest
from pathlib import Path
from aiwf.domain.profiles.workflow_profile import WorkflowProfile
from aiwf.domain.models.processing_result import ProcessingResult

def test_workflow_profile_is_abstract():
    """Verify WorkflowProfile is an abstract base class."""
    assert inspect.isabstract(WorkflowProfile)
    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        WorkflowProfile()

def test_workflow_profile_has_required_methods():
    """Verify all required methods exist."""
    methods = [
        "generate_planning_prompt",
        "generate_generation_prompt",
        "generate_review_prompt",
        "generate_revision_prompt",
        "process_planning_response",
        "process_generation_response",
        "process_review_response",
        "process_revision_response",
    ]
    for method in methods:
        assert hasattr(WorkflowProfile, method), f"Missing method: {method}"
        assert getattr(getattr(WorkflowProfile, method), "__isabstractmethod__"), f"Method {method} should be abstract"

def test_method_signatures():
    """Verify method signatures match requirements."""
    
    # generate_planning_prompt(self, context: dict) -> str
    sig = inspect.signature(WorkflowProfile.generate_planning_prompt)
    assert list(sig.parameters.keys()) == ["self", "context"]
    assert sig.parameters["context"].annotation == dict
    assert sig.return_annotation == str

    # generate_generation_prompt(self, context: dict) -> str
    sig = inspect.signature(WorkflowProfile.generate_generation_prompt)
    assert list(sig.parameters.keys()) == ["self", "context"]
    assert sig.parameters["context"].annotation == dict
    assert sig.return_annotation == str

    # generate_review_prompt(self, context: dict) -> str
    sig = inspect.signature(WorkflowProfile.generate_review_prompt)
    assert list(sig.parameters.keys()) == ["self", "context"]
    assert sig.parameters["context"].annotation == dict
    assert sig.return_annotation == str

    # generate_revision_prompt(self, context: dict) -> str
    sig = inspect.signature(WorkflowProfile.generate_revision_prompt)
    assert list(sig.parameters.keys()) == ["self", "context"]
    assert sig.parameters["context"].annotation == dict
    assert sig.return_annotation == str

    # process_planning_response(self, content: str) -> ProcessingResult
    sig = inspect.signature(WorkflowProfile.process_planning_response)
    assert list(sig.parameters.keys()) == ["self", "content"]
    assert sig.parameters["content"].annotation == str
    assert sig.return_annotation == ProcessingResult

    # process_generation_response(self, content: str, session_dir: Path, iteration: int) -> ProcessingResult
    sig = inspect.signature(WorkflowProfile.process_generation_response)
    assert list(sig.parameters.keys()) == ["self", "content", "session_dir", "iteration"]
    assert sig.parameters["content"].annotation == str
    assert sig.parameters["session_dir"].annotation == Path
    assert sig.parameters["iteration"].annotation == int
    assert sig.return_annotation == ProcessingResult

    # process_review_response(self, content: str) -> ProcessingResult
    sig = inspect.signature(WorkflowProfile.process_review_response)
    assert list(sig.parameters.keys()) == ["self", "content"]
    assert sig.parameters["content"].annotation == str
    assert sig.return_annotation == ProcessingResult

    # process_revision_response(self, content: str, session_dir: Path, iteration: int) -> ProcessingResult
    sig = inspect.signature(WorkflowProfile.process_revision_response)
    assert list(sig.parameters.keys()) == ["self", "content", "session_dir", "iteration"]
    assert sig.parameters["content"].annotation == str
    assert sig.parameters["session_dir"].annotation == Path
    assert sig.parameters["iteration"].annotation == int
    assert sig.return_annotation == ProcessingResult
