import asyncio
import inspect
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from time import perf_counter
from typing import Literal

from .graph import execution_layers, topological_order
from .models import Task, Workflow


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
    attempts: int = 0

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
                TaskStatus.FAILED, task_started_at, perf_counter(), error=exc, attempts=1
            )
            if first_failure is None:
                first_failure = (name, exc)
        else:
            task_states[name] = TaskState(
                TaskStatus.SUCCEEDED, task_started_at, perf_counter(), attempts=1
            )
            outputs[name] = output

    result = RunResult(outputs, task_states, started_at, perf_counter())
    if first_failure is not None:
        task_name, cause = first_failure
        raise TaskExecutionError(task_name, result) from cause
    return result


async def _attempt(task: Task, inputs: dict[str, object]) -> object:
    function = task.function
    worker: asyncio.Task[object] | None = None
    try:
        async with asyncio.timeout(task.timeout) as deadline:
            if inspect.iscoroutinefunction(function) or inspect.iscoroutinefunction(
                getattr(function, "__call__", None)
            ):
                output = function(inputs, task.params)
            else:
                worker = asyncio.create_task(asyncio.to_thread(function, inputs, task.params))
                output = await asyncio.shield(worker)
                worker = None

            if inspect.isawaitable(output):
                output = await output
        if deadline.expired():
            raise TimeoutError
        return output
    except TimeoutError:
        if worker is not None:
            # Nie zwalniaj miejsca ani nie ponawiaj, dopóki poprzedni wątek działa.
            await asyncio.wait({worker})
        raise
    finally:
        if worker is not None:
            worker.add_done_callback(_discard_worker_result)


def _discard_worker_result(worker: asyncio.Task[object]) -> None:
    if not worker.cancelled() and worker.exception() is None:
        output = worker.result()
        if inspect.iscoroutine(output):
            output.close()


async def _execute_task(
    task: Task,
    inputs: dict[str, object],
    slots: asyncio.Semaphore,
    base_delay: float,
    retry_backoff: Literal["exponential", "constant"],
) -> tuple[TaskState, object]:
    async with slots:
        started_at = perf_counter()
        delay = base_delay
        attempt = 1
        while True:
            try:
                output = await _attempt(task, inputs)
            except Exception as exc:
                if attempt == task.retries + 1:
                    return TaskState(
                        TaskStatus.FAILED, started_at, perf_counter(), exc, attempt
                    ), None
                await asyncio.sleep(delay)
                if retry_backoff == "exponential":
                    delay *= 2
                attempt += 1
            else:
                return TaskState(
                    TaskStatus.SUCCEEDED, started_at, perf_counter(), attempts=attempt
                ), output


async def async_run(
    workflow: Workflow,
    max_concurrency: int = 4,
    *,
    base_delay: float = 0.1,
    retry_backoff: Literal["exponential", "constant"] = "exponential",
) -> RunResult:
    if type(max_concurrency) is not int or max_concurrency < 1:
        raise ValueError("Limit współbieżności musi być dodatnią liczbą całkowitą.")
    if type(base_delay) not in (int, float) or not 0 <= base_delay < float("inf"):
        raise ValueError("Opóźnienie ponowienia musi być nieujemną, skończoną liczbą.")
    if retry_backoff not in ("exponential", "constant"):
        raise ValueError("Polityka ponowień musi mieć wartość 'exponential' lub 'constant'.")

    started_at = perf_counter()
    layers = execution_layers(workflow)
    slots = asyncio.Semaphore(max_concurrency)
    outputs: dict[str, object] = {}
    task_states: dict[str, TaskState] = {}
    first_failure: tuple[str, Exception] | None = None

    for layer in layers:
        running: dict[str, asyncio.Task[tuple[TaskState, object]]] = {}
        for name in layer:
            task = workflow.tasks[name]
            dependencies = sorted(task.dependencies)
            if all(dependency in outputs for dependency in dependencies):
                inputs = {dependency: outputs[dependency] for dependency in dependencies}
                running[name] = asyncio.create_task(
                    _execute_task(task, inputs, slots, base_delay, retry_backoff)
                )

        try:
            await asyncio.gather(*running.values())
        except BaseException:
            for pending in running.values():
                pending.cancel()
            await asyncio.gather(*running.values(), return_exceptions=True)
            raise

        for name in layer:
            if name not in running:
                task_states[name] = TaskState(TaskStatus.SKIPPED)
                continue
            state, output = running[name].result()
            task_states[name] = state
            if state.status is TaskStatus.SUCCEEDED:
                outputs[name] = output
            elif first_failure is None and state.error is not None:
                first_failure = (name, state.error)

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
        line = f"{name} [{state.status.value}] {elapsed}, próby: {state.attempts}"
        if state.error is not None:
            line += f", błąd: {type(state.error).__name__}: {state.error}"
        lines.append(line)
    status = "SUCCEEDED" if result.succeeded else "FAILED"
    lines.append(f"Cały przebieg [{status}] {result.duration:.6f} s")
    return "\n".join(lines)
