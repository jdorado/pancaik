"""
Asyncio Loop Utilities

This module provides helper functions for managing asyncio event loops,
particularly for running async code from a synchronous context or ensuring
coroutines run in the correct loop.
"""
import asyncio
import threading
from typing import Any, Callable, Coroutine


def run_in_new_loop(coro: Coroutine) -> Any:
    """
    Runs a coroutine in a new asyncio event loop in a separate thread.

    This is useful for calling async code from a synchronous context, especially
    when the main thread might have its own running event loop, which would
    prevent the use of `asyncio.run()`.

    Args:
        coro: The coroutine to execute.

    Returns:
        The result of the coroutine.
    """
    result = None
    exception = None
    lock = threading.Lock()
    lock.acquire()

    def thread_target():
        nonlocal result, exception
        try:
            result = asyncio.run(coro)
        except Exception as e:
            exception = e
        finally:
            lock.release()

    thread = threading.Thread(target=thread_target)
    thread.start()
    lock.acquire()  # Wait for the thread to finish
    thread.join()

    if exception:
        raise exception

    return result 