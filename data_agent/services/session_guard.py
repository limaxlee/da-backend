import asyncio
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class SessionBusyError(RuntimeError):
    """Raised when another writer holds the session and this one will not wait for it."""


class SessionGuard:
    """Serialises the writers of a single ADK session row.

    ``DatabaseSessionService.append_event`` refuses to write when the row moved in
    storage since the ``Session`` object was loaded, and a run keeps the ``Session``
    it loaded for its whole invocation. Any other append landing in that window
    kills the run. Everything that appends to a session therefore takes the guard
    first: runs hold it end to end, title writes only around their own append.

    The guard is per process. With several workers or replicas a database-level
    lock would be needed instead; the reload-and-retry in ``DBSessionService``
    covers the writers this cannot see.
    """

    def __init__(self):
        self._locks: dict[str, asyncio.Lock] = {}
        self._holders: dict[str, int] = {}

    def is_busy(self, session_id: str) -> bool:
        lock = self._locks.get(session_id)
        return lock is not None and lock.locked()

    @asynccontextmanager
    async def hold(self, session_id: str, timeout: float | None = None):
        """Take the write lock for a session, waiting up to ``timeout`` seconds.

        ``timeout=None`` waits indefinitely. A caller that is not prepared to wait
        out a full agent run passes a timeout and handles ``SessionBusyError``.
        """
        lock = self._locks.setdefault(session_id, asyncio.Lock())
        self._holders[session_id] = self._holders.get(session_id, 0) + 1

        try:
            if timeout is None:
                await lock.acquire()
            else:
                try:
                    await asyncio.wait_for(lock.acquire(), timeout)
                except asyncio.TimeoutError:
                    raise SessionBusyError(
                        f"Session {session_id} is still being written after waiting {timeout}s"
                    )

            try:
                yield
            finally:
                lock.release()
        finally:
            self._holders[session_id] -= 1
            if not self._holders[session_id]:
                del self._holders[session_id]
                self._locks.pop(session_id, None)
