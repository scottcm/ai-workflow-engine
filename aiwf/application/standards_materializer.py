import hashlib
from pathlib import Path
from typing import Any

from aiwf.application.standards_provider import StandardsProvider


def materialize_standards(
    *, 
    session_dir: Path, 
    context: dict[str, Any],
    provider: StandardsProvider
) -> str:
    """
    Materialize standards bundle and return hash.
    
    Returns:
        SHA256 hash of bundle
    """
    bundle_text = provider.create_bundle(context)
    bundle_hash = hashlib.sha256(bundle_text.encode("utf-8")).hexdigest()
    
    bundle_path = session_dir / "standards-bundle.md"
    bundle_path.write_text(bundle_text, encoding="utf-8")
    
    return bundle_hash


def read_standards_bundle(session_dir: Path) -> str:
    """Read standards bundle from session directory.
    
    Args:
        session_dir: Path to session directory
        
    Returns:
        Bundle content as string
        
    Raises:
        FileNotFoundError: If bundle doesn't exist
    """
    bundle_path = session_dir / "standards-bundle.md"
    return bundle_path.read_text(encoding='utf-8')