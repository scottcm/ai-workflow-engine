from pathlib import Path
from datetime import datetime
import json
import shutil
from typing import Any
from aiwf.domain.models.workflow_state import WorkflowState
from aiwf.domain.constants import (
    DEFAULT_SESSIONS_ROOT,
    SESSION_FILENAME,
    SESSION_TEMP_SUFFIX,
)


class SessionStore:
    """Handles persistence of workflow session state"""

    def __init__(self, sessions_root: Path | None = None):
        """
        Initialize the session store.
        
        Args:
            sessions_root: Root directory for all sessions (default: .aiwf/sessions)
        """
        self.sessions_root = sessions_root or DEFAULT_SESSIONS_ROOT
        self.sessions_root.mkdir(parents=True, exist_ok=True)

    def save(self, state: WorkflowState) -> Path:
        """
        Save workflow state to session.json
        
        Args:
            state: The workflow state to persist
            
        Returns:
            Path to the saved session.json file
            
        Raises:
            IOError: If save fails
        """
        session_dir = self.sessions_root / state.session_id
        session_dir.mkdir(parents=True, exist_ok=True)

        session_file = session_dir / SESSION_FILENAME
        temp_file = session_file.with_suffix(SESSION_TEMP_SUFFIX)

        state.updated_at = datetime.now()

        # Serialize to JSON
        data = self._serialize(state)

        # Write atomically - write to temp, then rename
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        temp_file.replace(session_file)

        return session_file
    
    def load(self, session_id: str) -> WorkflowState:
        """
        Load workflow state from session.json
        
        Args:
            session_id: The session identifier
            
        Returns:
            The loaded workflow state
            
        Raises:
            FileNotFoundError: If session doesn't exist
            ValueError: If session.json is invalid
        """
        session_file = self.sessions_root / session_id / SESSION_FILENAME

        if not session_file.exists():
            raise FileNotFoundError(
                f"Session '{session_id}' not found at {session_file}"
            )
        
        with open(session_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return self._deserialize(data)
    
    def exists(self, session_id: str) -> bool:
        """
        Check if a session exists.
        
        Args:
            session_id: The session identifier
            
        Returns:
            True if session exists, False otherwise
        """
        session_file = self.sessions_root / session_id / SESSION_FILENAME
        return session_file.exists()
    
    def list_sessions(self) -> list[str]:
        """
        List all session IDs.
        
        Returns:
            List of session identifiers
        """
        if not self.sessions_root.exists():
            return []
        
        sessions = []
        for session_dir in self.sessions_root.iterdir():
            if session_dir.is_dir() and (session_dir / SESSION_FILENAME).exists():
                sessions.append(session_dir.name)

        return sorted(sessions)
    
    def delete(self, session_id: str) -> None:
        """
        Delete a session and all its files.
        
        Args:
            session_id: The session identifier
            
        Raises:
            FileNotFoundError: If session doesn't exist
        """
        session_dir = self.sessions_root / session_id

        if not session_dir.exists():
            raise FileNotFoundError(f"Session '{session_id}' not found")
        
        # Remove all files in the directory
        shutil.rmtree(session_dir)

    def _serialize(self, state: WorkflowState) -> dict[str, Any]:
        """Convert WorkflowState to JSON-serializable dict."""
        return state.model_dump(mode='json')
    
    def _deserialize(self, data: dict[str, Any]) -> WorkflowState:
        """
        Convert JSON dict to WorkflowState.
        
        Args:
            data: Dictionary from JSON
            
        Returns:
            Reconstructed WorkflowState
            
        Raises:
            ValueError: If data is invalid
        """
        # Parse datetime strings
        if isinstance(data.get('created_at'), str):
            data['created_at'] = datetime.fromisoformat(data['created_at'])
        if isinstance(data.get('updated_at'), str):
            data['updated_at'] = datetime.fromisoformat(data['updated_at'])
        
        # Let Pydantic validate and construct
        try:
            return WorkflowState(**data)
        except Exception as e:
            raise ValueError(f"Invalid session data: {e}") from e