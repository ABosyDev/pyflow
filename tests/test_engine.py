import pytest

from pyflow import (
    Task,
    TaskExecutionError,
    TaskStatus,
    Workflow,
    WorkflowValidationE,
    format_report,
    run,
)


def test_runs_in_topological_order_and_passes_only_direct_outputs():
    calls = []

    def extract(inputs, params):
        calls.append("extract")
        assert inputs == {}
        assert params == {"value": 4}
        return params["value"]

    def transform(inputs, params):
        calls.append("transform")
        assert inputs == {"extract": 4}
        return inputs["extract"] * 2

    def report(inputs, params):
        calls.append("report")
        assert inputs == {"transform": 8}
        return None

    workflow = Workflow()
    workflow.add_task(Task("report", report, frozenset({"transform"})))
    workflow.add_task(Task("transform", transform, frozenset({"extract"})))
    workflow.add_task(Task("extract", extract, params={"value": 4}))

    result = run(workflow)

    assert calls == ["extract", "transform", "report"]
    assert result.outputs == {"extract": 4, "transform": 8, "report": None}
    assert result.succeeded
    for state in result.task_states.values():
        assert state.status is TaskStatus.SUCCEEDED
        assert state.error is None
        assert result.started_at <= state.started_at <= state.finished_at <= result.finished_at


def test_empty_workflow_succeeds():
    result = run(Workflow())

    assert result.succeeded
    assert result.outputs == {}
    assert result.task_states == {}
    assert result.duration >= 0


def test_invalid_workflow_is_rejected_before_running_any_task():
    def must_not_run(inputs, params):
        pytest.fail("Wywołano funkcję przed walidacją grafu")

    workflow = Workflow()
    workflow.add_task(Task("a", must_not_run))
    workflow.add_task(Task("b", must_not_run, frozenset({"missing"})))

    with pytest.raises(WorkflowValidationE, match="missing"):
        run(workflow)


def test_failure_skips_descendants_and_completes_the_independent_branch():
    cause = ValueError("Niepoprawne dane")
    second_cause = RuntimeError("Druga awaria")

    def fail(inputs, params):
        raise cause

    def fail_again(inputs, params):
        raise second_cause

    def must_not_run(inputs, params):
        pytest.fail("Wywołano zadanie zależne od awarii")

    def independent(inputs, params):
        return None

    def use_none(inputs, params):
        assert inputs == {"b_independent": None}
        return "ukończono"

    workflow = Workflow()
    workflow.add_task(Task("a_failure", fail))
    workflow.add_task(Task("b_independent", independent))
    workflow.add_task(Task("c_failure", fail_again))
    workflow.add_task(Task("skipped", must_not_run, frozenset({"a_failure", "b_independent"})))
    workflow.add_task(Task("descendant", must_not_run, frozenset({"skipped"})))
    workflow.add_task(Task("independent_child", use_none, frozenset({"b_independent"})))

    with pytest.raises(TaskExecutionError) as caught:
        run(workflow)

    error = caught.value
    assert error.task_name == "a_failure"
    assert error.__cause__ is cause
    result = error.result
    assert not result.succeeded
    assert result.outputs == {"b_independent": None, "independent_child": "ukończono"}
    assert {name: state.status for name, state in result.task_states.items()} == {
        "a_failure": TaskStatus.FAILED,
        "b_independent": TaskStatus.SUCCEEDED,
        "c_failure": TaskStatus.FAILED,
        "skipped": TaskStatus.SKIPPED,
        "descendant": TaskStatus.SKIPPED,
        "independent_child": TaskStatus.SUCCEEDED,
    }
    assert result.task_states["a_failure"].error is cause
    assert result.task_states["a_failure"].duration >= 0
    assert result.task_states["c_failure"].error is second_cause
    assert result.task_states["skipped"].duration is None
    report = format_report(result)
    assert "a_failure [FAILED]" in report
    assert "skipped [SKIPPED] —" in report
    assert "Cały przebieg [FAILED]" in report
