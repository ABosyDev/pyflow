import asyncio
from functools import wraps
from threading import Event

import pytest

from pyflow import (
    Task,
    TaskExecutionError,
    TaskStatus,
    Workflow,
    WorkflowValidationE,
    async_run,
    format_report,
)


def test_limits_concurrency_and_waits_for_the_whole_layer():
    async def scenario():
        pair_started = asyncio.Event()
        release_pair = asyncio.Event()
        active = 0
        peak = 0

        async def step(inputs, params):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            if active == 2:
                pair_started.set()
            await release_pair.wait()
            active -= 1
            return params["value"]

        async def child(inputs, params):
            assert active == 0
            assert inputs == {"a": 1}
            return inputs["a"] + 10

        workflow = Workflow()
        for name, value in zip("abc", (1, 2, 3)):
            workflow.add_task(Task(name, step, params={"value": value}))
        workflow.add_task(Task("child", child, frozenset({"a"})))
        execution = asyncio.create_task(async_run(workflow, max_concurrency=2))
        await pair_started.wait()
        assert active == 2
        release_pair.set()
        result = await execution
        assert peak == 2
        assert result.outputs == {"a": 1, "b": 2, "c": 3, "child": 11}
        assert result.task_states["c"].finished_at <= result.task_states["child"].started_at

    asyncio.run(asyncio.wait_for(scenario(), timeout=2))


def test_supports_sync_functions_decorators_and_async_callable_instances():
    async def scenario():
        loop = asyncio.get_running_loop()

        def sync_step(inputs, params):
            with pytest.raises(RuntimeError):
                asyncio.get_running_loop()
            return 3

        def sync_wrapper(function):
            @wraps(function)
            def wrapped(inputs, params):
                with pytest.raises(RuntimeError):
                    asyncio.get_running_loop()
                return function(inputs, params)

            return wrapped

        @sync_wrapper
        async def decorated(inputs, params):
            assert asyncio.get_running_loop() is loop
            return inputs["sync"] * 2

        class AsyncStep:
            async def __call__(self, inputs, params):
                assert asyncio.get_running_loop() is loop
                return inputs["decorated"] + 1

        workflow = Workflow()
        workflow.add_task(Task("sync", sync_step))
        workflow.add_task(Task("decorated", decorated, frozenset({"sync"})))
        workflow.add_task(Task("final", AsyncStep(), frozenset({"decorated"})))
        result = await async_run(workflow)
        assert result.outputs == {"sync": 3, "decorated": 6, "final": 7}

    asyncio.run(scenario())


@pytest.mark.parametrize(
    ("policy", "expected"), [("exponential", [0.25, 0.5]), ("constant", [0.25, 0.25])]
)
def test_retries_until_success_with_requested_backoff(monkeypatch, policy, expected):
    delays = []
    calls = 0

    async def record_sleep(delay):
        delays.append(delay)

    async def flaky(inputs, params):
        nonlocal calls
        calls += 1
        if calls <= 2:
            raise ValueError("Przejściowy błąd")
        return None

    monkeypatch.setattr("pyflow.engine.asyncio.sleep", record_sleep)
    workflow = Workflow()
    workflow.add_task(Task("flaky", flaky, retries=2))
    result = asyncio.run(async_run(workflow, base_delay=0.25, retry_backoff=policy))

    assert delays == expected
    assert result.outputs == {"flaky": None}
    assert result.task_states["flaky"].attempts == 3
    assert result.task_states["flaky"].error is None


def test_timeout_retries_then_skips_dependents_and_finishes_other_branch():
    calls = 0

    async def slow(inputs, params):
        nonlocal calls
        calls += 1
        await asyncio.Event().wait()

    async def skip(inputs, params):
        pytest.fail("Uruchomiono zadanie zależne od kroku zakończonego błędem")

    workflow = Workflow()
    workflow.add_task(Task("slow", slow, retries=1, timeout=0.01))
    workflow.add_task(Task("skip", skip, frozenset({"slow"})))
    workflow.add_task(Task("skip_child", skip, frozenset({"skip"})))
    workflow.add_task(Task("ok", lambda inputs, params: 42))
    workflow.add_task(Task("ok_child", lambda inputs, params: inputs["ok"], frozenset({"ok"})))

    with pytest.raises(TaskExecutionError) as caught:
        asyncio.run(async_run(workflow, max_concurrency=1, base_delay=0))

    result = caught.value.result
    failure = result.task_states["slow"]
    assert caught.value.task_name == "slow"
    assert failure.error is caught.value.__cause__
    assert isinstance(failure.error, TimeoutError)
    assert failure.status is TaskStatus.FAILED
    assert failure.attempts == calls == 2
    assert result.outputs == {"ok": 42, "ok_child": 42}
    for name in ("skip", "skip_child"):
        assert result.task_states[name].status is TaskStatus.SKIPPED
        assert result.task_states[name].attempts == 0
    assert "próby: 2, błąd: TimeoutError" in format_report(result)


def test_sync_timeout_keeps_slot_until_thread_finishes():
    async def scenario():
        loop = asyncio.get_running_loop()
        started = asyncio.Event()
        release = Event()
        calls = 0

        def sync_step(inputs, params):
            nonlocal calls
            calls += 1
            loop.call_soon_threadsafe(started.set)
            assert release.wait(2)
            return "po czasie"

        async def independent(inputs, params):
            assert release.is_set()
            return "gotowe"

        workflow = Workflow()
        workflow.add_task(Task("a_sync", sync_step, timeout=0.02))
        workflow.add_task(Task("b_independent", independent))
        execution = asyncio.create_task(async_run(workflow, max_concurrency=1))
        await started.wait()
        loop.call_later(0.05, release.set)

        with pytest.raises(TaskExecutionError) as caught:
            await execution

        assert calls == 1
        assert isinstance(caught.value.__cause__, TimeoutError)
        assert caught.value.result.outputs == {"b_independent": "gotowe"}

    asyncio.run(asyncio.wait_for(scenario(), timeout=3))


@pytest.mark.parametrize("from_parent", [True, False])
def test_cancellation_propagates_without_retry_and_cancels_siblings(from_parent):
    async def scenario():
        sibling_started = asyncio.Event()
        sibling_stopped = asyncio.Event()
        calls = 0

        async def cancel(inputs, params):
            nonlocal calls
            calls += 1
            await sibling_started.wait()
            if not from_parent:
                raise asyncio.CancelledError
            await asyncio.Event().wait()

        async def sibling(inputs, params):
            sibling_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                sibling_stopped.set()

        workflow = Workflow()
        workflow.add_task(Task("cancel", cancel, retries=3))
        workflow.add_task(Task("sibling", sibling))
        execution = asyncio.create_task(async_run(workflow, base_delay=0))
        await sibling_started.wait()
        if from_parent:
            execution.cancel()
        with pytest.raises(asyncio.CancelledError):
            await execution
        assert calls == 1
        assert sibling_stopped.is_set()

    asyncio.run(asyncio.wait_for(scenario(), timeout=2))


def test_validates_graph_and_limit_before_running_any_task():
    def must_not_run(inputs, params):
        pytest.fail("Uruchomiono zadanie przed walidacją")

    workflow = Workflow()
    workflow.add_task(Task("ready", must_not_run))
    workflow.add_task(Task("invalid", must_not_run, frozenset({"missing"}), retries=3))

    with pytest.raises(ValueError, match="Limit współbieżności"):
        asyncio.run(async_run(workflow, max_concurrency=0))
    with pytest.raises(WorkflowValidationE, match="missing"):
        asyncio.run(async_run(workflow, base_delay=0))


@pytest.mark.parametrize("options", [{"retries": -1}, {"timeout": 0}, {"timeout": float("nan")}])
def test_rejects_invalid_task_options(options):
    with pytest.raises(WorkflowValidationE):
        Task("invalid", lambda inputs, params: None, **options)
