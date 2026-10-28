import pytest

from pyflow import Task, Workflow, WorkflowValidationE, execution_layers, topological_order


def example_function(inputs, params):
    return None


def make_workflow(definitions):
    workflow = Workflow()
    for name, dependencies in definitions:
        workflow.add_task(Task(name, example_function, frozenset(dependencies)))
    return workflow


@pytest.mark.parametrize(
    "definitions, expected",
    [
        ([], []),
        ([("a", [])], [["a"]]),
        ([("c", ["b"]), ("b", ["a"]), ("a", [])], [["a"], ["b"], ["c"]]),
        ([("b", []), ("a", [])], [["a", "b"]]),
        (
            [("report", ["clean_a", "clean_b"]), ("clean_b", ["extract"]),
             ("extract", []), ("clean_a", ["extract"])],
            [["extract"], ["clean_a", "clean_b"], ["report"]],
        ),
    ],
)
def test_execution_plan(definitions, expected):
    workflow = make_workflow(definitions)
    workflow.validate()
    assert execution_layers(workflow) == expected
    assert topological_order(workflow) == [name for layer in expected for name in layer]


@pytest.mark.parametrize("operation", [Workflow.validate, execution_layers, topological_order])
def test_missing_dependency(operation):
    workflow = make_workflow([("a", ["missing"])])
    with pytest.raises(WorkflowValidationE, match="missing"):
        operation(workflow)


@pytest.mark.parametrize("operation", [Workflow.validate, execution_layers, topological_order])
def test_cycle(operation):
    workflow = make_workflow([("a", ["b"]), ("b", ["a"]), ("independent", [])])
    with pytest.raises(WorkflowValidationE, match="cykl"):
        operation(workflow)


def test_deterministic_order():
    definitions = [("c", ["a"]), ("b", []), ("a", [])]
    first = make_workflow(definitions)
    second = make_workflow(reversed(definitions))
    assert topological_order(first) == topological_order(second)
    assert execution_layers(first) == execution_layers(second)


def test_dependencies_are_in_earlier_layers():
    workflow = make_workflow([("a", []), ("b", ["a"]), ("c", ["a", "b"])])
    completed = set()
    order = topological_order(workflow)
    assert len(order) == len(set(order)) == len(workflow.tasks)
    for layer in execution_layers(workflow):
        for name in layer:
            assert workflow.tasks[name].dependencies <= completed
        completed.update(layer)
