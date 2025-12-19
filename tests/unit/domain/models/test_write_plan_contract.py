from aiwf.domain.models.write_plan import WriteOp, WritePlan


def test_write_op_contract_fields() -> None:
    op = WriteOp(path="src/Foo.java", content="class Foo {}")
    assert op.path == "src/Foo.java"
    assert op.content == "class Foo {}"

    assert "path" in WriteOp.model_fields
    assert "content" in WriteOp.model_fields


def test_write_plan_defaults_to_empty_writes_list() -> None:
    plan = WritePlan()
    assert plan.writes == []

    assert "writes" in WritePlan.model_fields


def test_write_plan_accepts_writes_list() -> None:
    plan = WritePlan(writes=[WriteOp(path="a.txt", content="x")])
    assert len(plan.writes) == 1
    assert plan.writes[0].path == "a.txt"
    assert plan.writes[0].content == "x"
