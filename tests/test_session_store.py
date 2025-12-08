"""Test SessionStore persistence (Phase 1)."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from aiwf.domain.persistence import SessionStore
from aiwf.domain.models import WorkflowState, WorkflowPhase, ExecutionMode


def test_session_store():
    """Test SessionStore save, load, list, delete operations."""
    
    # Use a temp directory for testing
    test_root = Path(".aiwf/test-sessions")
    store = SessionStore(sessions_root=test_root)
    
    try:
        # Create a test state with updated signature
        state = WorkflowState(
            session_id="test-20241207-001",
            profile="jpa-mt",
            scope="domain",
            phase=WorkflowPhase.INITIALIZED,
            execution_mode=ExecutionMode.INTERACTIVE,
            current_iteration=1,
            entity="Product",
            bounded_context=None,
            providers={"planner": "gemini", "coder": "claude"},
            artifacts=[],
            pending_action=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            phase_history=[]
        )
        
        print("1. Testing save...")
        saved_path = store.save(state)
        print(f"   ✓ Saved to: {saved_path}")
        assert saved_path.exists()
        
        print("2. Testing exists...")
        assert store.exists("test-20241207-001")
        print("   ✓ Session exists")
        
        print("3. Testing load...")
        loaded = store.load("test-20241207-001")
        assert loaded.session_id == state.session_id
        assert loaded.profile == "jpa-mt"
        assert loaded.scope == "domain"
        assert loaded.entity == "Product"
        assert loaded.current_iteration == 1
        print("   ✓ Loaded successfully")
        
        print("4. Testing list_sessions...")
        sessions = store.list_sessions()
        assert "test-20241207-001" in sessions
        print(f"   ✓ Found sessions: {sessions}")
        
        print("5. Testing delete...")
        store.delete("test-20241207-001")
        assert not store.exists("test-20241207-001")
        print("   ✓ Session deleted")
        
        print("\n✅ All SessionStore tests passed!")
        
    finally:
        # Cleanup
        if test_root.exists():
            shutil.rmtree(test_root)


if __name__ == "__main__":
    test_session_store()