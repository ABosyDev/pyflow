from .models import Workflow, WorkflowValidationE


def execution_layers(workflow: Workflow) -> list[list[str]]:
    tasks = workflow.tasks
    remaining = {}
    dependents: dict[str, list[str]] = {name: [] for name in tasks}

    for name, task in tasks.items():
        missing = task.dependencies - tasks.keys()
        if missing:
            raise WorkflowValidationE(
                f"Zadanie {name!r}: brakujące zależności: {', '.join(sorted(missing))}."
            )
        remaining[name] = len(task.dependencies)
        for dependency in task.dependencies:
            dependents[dependency].append(name)

    ready = sorted(name for name in tasks if remaining[name] == 0)
    layers = []
    processed = 0

    while ready:
        layers.append(ready)
        processed += len(ready)
        next_layer = []
        for name in ready:
            for dependent in dependents[name]:
                remaining[dependent] -= 1
                if remaining[dependent] == 0:
                    next_layer.append(dependent)
        ready = sorted(next_layer)

    if processed != len(tasks):
        blocked = sorted(name for name in tasks if remaining[name] > 0)
        raise WorkflowValidationE(
            f"Wykryto cykl. Zadania zablokowane: {', '.join(blocked)}."
        )
    return layers


def topological_order(workflow: Workflow) -> list[str]:
    return [name for layer in execution_layers(workflow) for name in layer]
