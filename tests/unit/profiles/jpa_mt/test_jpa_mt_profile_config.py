from typing import Any

import pytest
from pydantic import ValidationError

from profiles.jpa_mt.jpa_mt_profile import JpaMtProfile


def _valid_config() -> dict[str, Any]:
    return {
        "standards": {"root": "${STANDARDS_DIR}"},
        "scopes": {"domain": {"layers": ["entity"]}},
        "layer_standards": {
            "_universal": ["core/ORG.md"],
            "entity": ["db/java/JPA_AND_DATABASE.md"],
        },
        "artifacts": {"session_root": ".aiwf/sessions"},  # legacy; ignored
    }


def test_profile_accepts_kwargs_validates_and_stores_normalized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STANDARDS_DIR", "/tmp/standards")

    profile = JpaMtProfile(**_valid_config())

    assert isinstance(profile.config, dict)
    assert profile.config["standards"]["root"] == "/tmp/standards"
    assert "artifacts" not in profile.config


def test_profile_bad_config_raises_validationerror(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STANDARDS_DIR", "/tmp/standards")

    cfg = _valid_config()
    cfg["layer_standards"]["entity"] = ["/abs.md"]

    with pytest.raises(ValidationError):
        JpaMtProfile(**cfg)
