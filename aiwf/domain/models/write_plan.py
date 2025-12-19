from pydantic import BaseModel, Field


class WriteOp(BaseModel):
    path: str
    content: str


class WritePlan(BaseModel):
    writes: list[WriteOp] = Field(default_factory=list)
