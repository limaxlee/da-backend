import asyncio

import pytest

from data_agent.services.session_guard import SessionBusyError, SessionGuard


class TestSessionGuard:
    @pytest.mark.asyncio
    async def test_is_busy(self):
        guard = SessionGuard()

        assert guard.is_busy("s1") is False

        async with guard.hold("s1"):
            assert guard.is_busy("s1") is True
            assert guard.is_busy("s2") is False

        assert guard.is_busy("s1") is False

    @pytest.mark.asyncio
    async def test_hold_serialises_writers_of_one_session(self):
        guard = SessionGuard()
        order = []

        async def write(name, delay):
            async with guard.hold("s1"):
                order.append(f"{name} in")
                await asyncio.sleep(delay)
                order.append(f"{name} out")

        await asyncio.gather(write("first", 0.02), write("second", 0))

        assert order == ["first in", "first out", "second in", "second out"]

    @pytest.mark.asyncio
    async def test_hold_does_not_serialise_different_sessions(self):
        guard = SessionGuard()

        async with guard.hold("s1"):
            async with guard.hold("s2", timeout=0.01):
                assert guard.is_busy("s1") and guard.is_busy("s2")

    @pytest.mark.asyncio
    async def test_hold_times_out(self):
        guard = SessionGuard()

        async with guard.hold("s1"):
            with pytest.raises(SessionBusyError):
                async with guard.hold("s1", timeout=0.01):
                    pytest.fail("the guard was handed out twice")

    @pytest.mark.asyncio
    async def test_hold_releases_on_failure(self):
        guard = SessionGuard()

        with pytest.raises(RuntimeError):
            async with guard.hold("s1"):
                raise RuntimeError("write failed")

        assert guard.is_busy("s1") is False

    @pytest.mark.asyncio
    async def test_hold_forgets_sessions_nobody_is_using(self):
        """The registry is process wide, so it has to shrink back to empty."""
        guard = SessionGuard()

        async def write():
            async with guard.hold("s1"):
                await asyncio.sleep(0)

        await asyncio.gather(write(), write(), write())

        assert guard._locks == {}
        assert guard._holders == {}
