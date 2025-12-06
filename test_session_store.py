from aiwf.domain.persistence import SessionStore
from aiwf.domain.models import WorkflowState, WorkflowPhase, ExecutionMode
from datetime import datetime
from pathlib import Path

# Use a temp directory for testing
test_root = Path(".aiwf/test-sessions")
store = SessionStore(sessions_root=test_root)

# Create a test state
state = WorkflowState(
    session_id="test-20241205-001",
    profile="jpa-mt-domain",
    phase=WorkflowPhase.INITIALIZED,
    execution_mode=ExecutionMode.INTERACTIVE,
    entity="Product",
    providers={"planner": "gemini", "coder": "claude"},
    created_at=datetime.now(),
    updated_at=datetime.now()
)

print("1. Testing save...")
saved_path = store.save(state)
print(f"   ✓ Saved to: {saved_path}")

print("2. Testing exists...")
assert store.exists("test-20241205-001")
print("   ✓ Session exists")

print("3. Testing load...")
loaded = store.load("test-20241205-001")
assert loaded.session_id == state.session_id
assert loaded.entity == "Product"
print("   ✓ Loaded successfully")

print("4. Testing list_sessions...")
sessions = store.list_sessions()
assert "test-20241205-001" in sessions
print(f"   ✓ Found sessions: {sessions}")

print("5. Testing delete...")
store.delete("test-20241205-001")
assert not store.exists("test-20241205-001")
print("   ✓ Session deleted")

# Cleanup
import shutil
shutil.rmtree(test_root)
print("\n✅ All tests passed!")