from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from time import perf_counter

from .graph import topological_order
from .models import Workflow


class TaskStatus(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class TaskState:
    status: TaskStatus
    started_at: float | None = None
    finished_at: float | None = None
    error: Exception | None = None

    @property
    def duration(self) -> float | None:
        if self.started_at is None or self.finished_at is None:
            return None
        return self.finished_at - self.started_at


@dataclass(frozen=True)
class RunResult:
    outputs: Mapping[str, object]
    task_states: Mapping[str, TaskState]
    started_at: float
    finished_at: float

    @property
    def succeeded(self) -> bool:
        return all(state.status is TaskStatus.SUCCEEDED for state in self.task_states.values())

    @property
    def duration(self) -> float:
        return self.finished_at - self.started_at


class TaskExecutionError(RuntimeError):
    def __init__(self, task_name: str, result: RunResult) -> None:
        super().__init__(f"Zadanie {task_name!r} zakończyło się błędem.")
        self.task_name = task_name
        self.result = result


def run(workflow: Workflow) -> RunResult:
    started_at = perf_counter()
    # Planer sprawdza cały graf przed wywołaniem pierwszej funkcji.
    order = topological_order(workflow)
    outputs: dict[str, object] = {}
    task_states: dict[str, TaskState] = {}
    first_failure: tuple[str, Exception] | None = None

    for name in order:
        task = workflow.tasks[name]
        dependencies = sorted(task.dependencies)
        if any(dependency not in outputs for dependency in dependencies):
            task_states[name] = TaskState(TaskStatus.SKIPPED)
            continue

        inputs = {dependency: outputs[dependency] for dependency in dependencies}
        task_started_at = perf_counter()
        try:
            output = task.function(inputs, task.params)
        except Exception as exc:
            task_states[name] = TaskState(
                TaskStatus.FAILED, task_started_at, perf_counter(), error=exc
            )
            if first_failure is None:
                first_failure = (name, exc)
        else:
            task_states[name] = TaskState(
                TaskStatus.SUCCEEDED, task_started_at, perf_counter()
            )
            outputs[name] = output

    result = RunResult(outputs, task_states, started_at, perf_counter())
    if first_failure is not None:
        task_name, cause = first_failure
        raise TaskExecutionError(task_name, result) from cause
    return result


def format_report(result: RunResult) -> str:
    lines = []
    for name, state in result.task_states.items():
        duration = state.duration
        elapsed = f"{duration:.6f} s" if duration is not None else "—"
        lines.append(f"{name} [{state.status.value}] {elapsed}")
    status = "SUCCEEDED" if result.succeeded else "FAILED"
    lines.append(f"Cały przebieg [{status}] {result.duration:.6f} s")
    return "\n".join(lines)
