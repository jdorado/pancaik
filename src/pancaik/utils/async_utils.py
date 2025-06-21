import asyncio
import functools
from concurrent.futures import ThreadPoolExecutor

# Single shared executor for all decorated functions
_THREAD_POOL = ThreadPoolExecutor()


def force_async(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        loop = asyncio.get_running_loop()
        return loop.run_in_executor(_THREAD_POOL, fn, *args, **kwargs)

    return wrapper


def force_sync(fn):
    """
    Decorator to run an async function in a sync context.
    It ensures an event loop is running in the current thread.
    """

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        coro = fn(*args, **kwargs)
        if not asyncio.iscoroutine(coro):
            return coro

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No event loop in this thread.
            # Create a new one, run the coroutine, and close it.
            return asyncio.run(coro)

        if loop.is_running():
            # Loop is running, but we are in a sync function.
            # This can happen if a sync function is called from an async one.
            # To avoid blocking the running loop, we can run the coroutine
            # in a thread pool executor, but our `force_async` already does that.
            # Here, we need to run an async function from a sync context,
            # which implies the caller is prepared to be blocked.
            # The safest way to run a coroutine on a loop in another thread
            # is using run_coroutine_threadsafe.
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result()
        else:
            # Loop exists but is not running.
            return loop.run_until_complete(coro)

    return wrapper
