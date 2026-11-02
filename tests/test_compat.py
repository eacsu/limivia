"""跨解释器验证超时、取消和异常诊断，使用真实 asyncio 调度。"""

import asyncio

import pytest

from limivia import ResourceCleanupError, ResultUnknownError
from limivia._compat import add_note, timeout_after, wait_for
from limivia._lifecycle import record_cleanup


async def deadline_wait(awaitable, delay):
    async with timeout_after(delay):
        return await awaitable


@pytest.mark.parametrize("wait", [deadline_wait, wait_for])
def test_timeout_is_builtin_and_shielded_work_survives(wait):
    async def run():
        pending = asyncio.get_running_loop().create_future()
        with pytest.raises(TimeoutError) as caught:
            await wait(asyncio.shield(pending), 0.01)
        assert type(caught.value) is TimeoutError
        assert not pending.done()
        pending.set_result(42)
        assert await wait(pending, None) == 42
        # 超时作用域退出后，不应留下稍后再次取消调用方的定时器。
        await asyncio.sleep(0)

    asyncio.run(run())


@pytest.mark.parametrize("wait", [deadline_wait, wait_for])
def test_external_cancellation_is_not_timeout(wait):
    async def run():
        started = asyncio.Event()
        finalized = asyncio.Event()

        async def work():
            try:
                started.set()
                await asyncio.Event().wait()
            finally:
                finalized.set()

        task = asyncio.create_task(wait(work(), 60))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert finalized.is_set()

    asyncio.run(run())


@pytest.mark.parametrize("wait", [deadline_wait, wait_for])
@pytest.mark.parametrize("error_type", [TimeoutError, ResultUnknownError])
def test_existing_timeout_error_keeps_identity_and_diagnostics(wait, error_type):
    async def run():
        original = error_type("device result unknown")
        add_note(original, "do not replay")

        async def work():
            raise original

        with pytest.raises(error_type) as caught:
            await wait(work(), 60)
        assert caught.value is original
        assert caught.value.__notes__ == ["do not replay"]

    asyncio.run(run())


@pytest.mark.parametrize("wait", [deadline_wait, wait_for])
def test_asyncio_timeout_from_inner_library_is_normalized(wait):
    async def run():
        async def work():
            raise asyncio.TimeoutError("transport deadline")

        with pytest.raises(TimeoutError, match="transport deadline"):
            await wait(work(), None)

    asyncio.run(run())


@pytest.mark.parametrize("outer_first", [True, False])
def test_nested_deadlines_remain_usable_after_timeout(outer_first):
    async def run():
        outer, inner = (0.01, 60) if outer_first else (60, 0.01)
        with pytest.raises(TimeoutError):
            async with timeout_after(outer), timeout_after(inner):
                await asyncio.Event().wait()
        async with timeout_after(None):
            await asyncio.sleep(0)

    asyncio.run(run())


@pytest.mark.parametrize("error_type", [ValueError, asyncio.CancelledError])
def test_cleanup_preserves_primary_error_and_existing_notes(error_type):
    original = error_type("original")
    add_note(original, "existing note")
    cleanup_error = ResourceCleanupError("release unconfirmed")
    record_cleanup(original, cleanup_error)
    record_cleanup(original, cleanup_error)
    assert str(original) == "original"
    assert original.cleanup_errors == [cleanup_error]
    assert original.__notes__ == [
        "existing note",
        "另有清理失败：ResourceCleanupError: release unconfirmed",
    ]
