from pathlib import Path
from typing import Protocol, Any


class StandardsProvider(Protocol):
    def create_bundle(self, context: dict[str, Any]) -> str:
        ...
