from typing import Literal
from pydantic import BaseModel


class BaseOutput(BaseModel):
    schema_version: int = 1
    command: Literal["init", "step", "status"]
    exit_code: int
    error: str | None = None


class InitOutput(BaseOutput):
    command: Literal["init"] = "init"
    # On init errors, session_id may be unknown; omit it from JSON via exclude_none.
    session_id: str | None = None


class StepOutput(BaseOutput):
    command: Literal["step"] = "step"
    session_id: str
    phase: str | None = None
    status: str | None = None
    iteration: int | None = None
    noop_awaiting_artifact: bool = False
    awaiting_paths: list[str] = []


class StatusOutput(BaseOutput):
    command: Literal["status"] = "status"
    session_id: str
    phase: str | None = None
    status: str | None = None
    iteration: int | None = None
    session_path: str
