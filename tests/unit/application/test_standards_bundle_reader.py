from typing import Any
from pathlib import Path
import pytest

from aiwf.application.standards_materializer import read_standards_bundle
from aiwf.application.standards_materializer import materialize_standards

class _Provider:
    def create_bundle(self, context: dict[str, Any]) -> str:
        return "--- X.md ---\nX\n"


def test_materialize_then_read_round_trip(tmp_path: Path) -> None:
    provider = _Provider()

    materialize_standards(
        session_dir=tmp_path,
        context={"scope": "domain"},
        provider=provider,
    )

    assert read_standards_bundle(tmp_path) == "--- X.md ---\nX\n"

def test_read_standards_bundle_reads_existing_file(tmp_path: Path) -> None:
    p = tmp_path / "standards-bundle.md"
    p.write_text("HELLO\nWORLD\n", encoding="utf-8")

    assert read_standards_bundle(tmp_path) == "HELLO\nWORLD\n"

def test_read_standards_bundle_raises_if_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_standards_bundle(tmp_path)
