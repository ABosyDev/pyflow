from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


class WorkflowValidationE(ValueError):
    pass


@dataclass(frozen=True)
class Task:
    name: str
    function: Callable[[Mapping[str, Any], Mapping[str, Any]], Any]
    dependencies: frozenset[str] = field(default_factory=frozenset)
    params: Mapping[str, Any] = field(default_factory=dict)
    description: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise WorkflowValidationE("Nazwa zadania nie może być pusta.")
        if self.name in self.dependencies:
            raise WorkflowValidationE(f"Zadanie {self.name!r} zależy od siebie.")
        if not callable(self.function):
            raise WorkflowValidationE("Funkcja zadania musi być wywoływalna.")
        object.__setattr__(self, "dependencies", frozenset(self.dependencies))
        object.__setattr__(self, "params", deepcopy(dict(self.params)))


class Workflow:
    def __init__(self) -> None:
        self.tasks: dict[str, Task] = {}

    def add_task(self, task: Task) -> None:
        if task.name in self.tasks:
            raise WorkflowValidationE(f"Zadanie {task.name!r} już istnieje.")
        self.tasks[task.name] = task

    def validate(self) -> None:
        from .graph import execution_layers

        execution_layers(self)
