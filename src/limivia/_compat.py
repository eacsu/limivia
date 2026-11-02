"""Python 3.10～3.12 的超时与异常备注兼容，保留 asyncio 取消语义。"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from typing import TypeVar

if sys.version_info >= (3, 11):
    from asyncio import timeout as _timeout
else:
    from async_timeout import timeout as _timeout

T = TypeVar("T")


@asynccontextmanager
async def timeout_after(delay: float | None) -> AsyncIterator[None]:
    """超时统一抛内置 TimeoutError；外部取消继续原样传播。"""
    try:
        async with _timeout(delay):
            yield
    except asyncio.TimeoutError as exc:
        if isinstance(exc, TimeoutError):
            raise
        raise TimeoutError(*exc.args) from exc


async def wait_for(awaitable: Awaitable[T], timeout: float | None) -> T:
    """保持 wait_for 的任务行为，仅统一旧版 asyncio 的超时异常。"""
    try:
        return await asyncio.wait_for(awaitable, timeout)
    except asyncio.TimeoutError as exc:
        if isinstance(exc, TimeoutError):
            raise
        raise TimeoutError(*exc.args) from exc


def add_note(error: BaseException, note: str) -> None:
    """3.10 保留 __notes__ 供诊断读取；新版本使用原生备注接口。"""
    if sys.version_info >= (3, 11):
        error.add_note(note)
    else:
        notes = getattr(error, "__notes__", None)
        if notes is None:
            notes = []
            error.__notes__ = notes  # type: ignore[attr-defined]
        notes.append(note)
