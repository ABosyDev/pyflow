import pytest

from pyflow import Task, Workflow, WorkflowValidationE


def example_function(inputs, params):
    return params


@pytest.mark.parametrize("name", ["", "   "])
def test_empty_name(name):
    with pytest.raises(WorkflowValidationE, match="pusta"):
        Task(name, example_function)


def test_self_dependency():
    with pytest.raises(WorkflowValidationE, match="od siebie"):
        Task("a", example_function, dependencies=frozenset({"a"}))


def test_duplicate():
    workflow = Workflow()
    workflow.add_task(Task("a", example_function))
    with pytest.raises(WorkflowValidationE, match="już istnieje"):
        workflow.add_task(Task("a", example_function))


def test_task_copies_input_data():
    dependencies = {"a"}
    params = {"values": [1, 2]}
    task = Task("b", example_function, dependencies=dependencies, params=params)
    dependencies.add("c")
    params["values"].append(3)
    assert task.dependencies == frozenset({"a"})
    assert task.params == {"values": [1, 2]}


def test_invalid_function():
    with pytest.raises(WorkflowValidationE, match="wywoływalna"):
        Task("a", None)
