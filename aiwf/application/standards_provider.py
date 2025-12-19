from pathlib import Path
from typing import Protocol, Any


class StandardsProvider(Protocol):
    def create_bundle(self, context: object) -> str:
        ...


class FileBasedStandardsProvider:
    def __init__(self, *, standards_root: Path, standards_files: list[str]):
        self.standards_root = standards_root
        self.standards_files = standards_files

    def create_bundle(self, context: Any) -> str:
        bundle_parts = []
        # Sort filenames lexically and deduplicate
        unique_files = sorted(set(self.standards_files))
        
        for filename in unique_files:
            file_path = self.standards_root / filename
            if not file_path.exists():
                raise FileNotFoundError(f"Standard file not found: {file_path}")
            
            # Read UTF-8 text
            content = file_path.read_text(encoding="utf-8")
            
            # Ensure a trailing newline after content (add one if missing)
            if not content.endswith("\n"):
                content += "\n"
                
            bundle_parts.append(f"--- {filename} ---\n{content}")
            
        return "".join(bundle_parts)