from pathlib import Path
from typing import Any


class JpaMtStandardsProvider:
    """
    Standards provider for JPA-MT profile.
    
    Implements scope-aware standards bundling based on
    JPA-MT's layer_standards configuration.
    """
    
    def __init__(self, config: dict[str, Any]):
        self.standards_root = Path(config['standards']['root'])
        self.scopes = config['scopes']
        self.layer_standards = config['layer_standards']
    
    def create_bundle(self, context: dict[str, Any]) -> str:
        scope = None
        if isinstance(context, dict):
            scope = context.get('scope')

        if not scope or scope not in self.scopes:
            raise ValueError(f"Unknown scope: {scope}")
        
        layers = self.scopes[scope]['layers']
        
        # Collect standards files preserving order:
        # 1. _universal
        # 2. layers in scope order
        # Deduplicate preserving first occurrence
        ordered_files: list[str] = []
        seen: set[str] = set()

        def add_files(file_list: list[str]) -> None:
            for f in file_list:
                if f not in seen:
                    ordered_files.append(f)
                    seen.add(f)

        if '_universal' in self.layer_standards:
            add_files(self.layer_standards['_universal'])
        
        for layer in layers:
            if layer in self.layer_standards:
                add_files(self.layer_standards[layer])
        
        # Read and concatenate
        bundle_parts = []
        for filename in ordered_files:
            file_path = self.standards_root / filename
            if not file_path.exists():
                raise FileNotFoundError(f"Standards file not found: {file_path}")
            
            content = file_path.read_text(encoding='utf-8')
            if not content.endswith('\n'):
                content += '\n'
            
            bundle_parts.append(f"--- {filename} ---\n{content}")
        
        return "".join(bundle_parts)
    