import hashlib
from pathlib import Path
from typing import Any

import pytest

from aiwf.application.standards_materializer import materialize_standards


class _Provider:
    def __init__(self, bundle: str) -> None:
        self._bundle = bundle

    def create_bundle(self, context: dict[str, Any]) -> str:
        return self._bundle


class _FailingProvider:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def create_bundle(self, context: dict[str, Any]) -> str:
        raise self._exc


def _sha256_hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def test_materialize_standards_writes_bundle_and_returns_hash(tmp_path: Path) -> None:
    bundle = "--- A.md ---\nalpha\n--- B.md ---\nbeta\n"
    provider = _Provider(bundle)

    h = materialize_standards(session_dir=tmp_path, context={"scope": "domain"}, provider=provider)

    bundle_path = tmp_path / "standards-bundle.md"
    assert bundle_path.exists()
    assert bundle_path.read_text(encoding="utf-8") == bundle
    assert h == _sha256_hex(bundle)


def test_materialize_standards_is_deterministic(tmp_path: Path) -> None:
    bundle = "--- X.md ---\nX\n"
    provider = _Provider(bundle)

    h1 = materialize_standards(session_dir=tmp_path, context={"scope": "domain"}, provider=provider)
    b1 = (tmp_path / "standards-bundle.md").read_bytes()

    h2 = materialize_standards(session_dir=tmp_path, context={"scope": "domain"}, provider=provider)
    b2 = (tmp_path / "standards-bundle.md").read_bytes()

    assert h1 == h2
    assert b1 == b2


def test_materialize_standards_provider_failure_is_hard_failure_no_write(tmp_path: Path) -> None:
    provider = _FailingProvider(RuntimeError("boom"))

    with pytest.raises(RuntimeError, match="boom"):
        materialize_standards(session_dir=tmp_path, context={"scope": "domain"}, provider=provider)

    assert not (tmp_path / "standards-bundle.md").exists()
