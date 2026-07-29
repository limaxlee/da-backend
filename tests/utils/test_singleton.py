import threading

import pytest

from data_agent.utils.singleton import singleton


class TestSingleton:

    @pytest.fixture
    def decorated_class(self):
        @singleton
        class Service:
            def __init__(self, value=None, **kwargs):
                self.value = value
                self.kwargs = kwargs

        return Service

    def test_returns_callable_instead_of_class(self, decorated_class):
        assert not isinstance(decorated_class, type)
        assert callable(decorated_class)

    def test_returns_same_instance_on_repeated_calls(self, decorated_class):
        first = decorated_class()
        second = decorated_class()

        assert first is second

    def test_first_call_arguments_are_used(self, decorated_class):
        first = decorated_class("initial", extra=1)
        second = decorated_class("ignored", extra=2)

        assert second is first
        assert second.value == "initial"
        assert second.kwargs == {"extra": 1}

    def test_class_is_constructed_only_once(self, mocker):
        init_spy = mocker.MagicMock(return_value=None)

        @singleton
        class Service:
            def __init__(self, *args, **kwargs):
                init_spy(*args, **kwargs)

        Service("a")
        Service("b")
        Service("c")

        init_spy.assert_called_once_with("a")

    def test_different_decorated_classes_have_separate_instances(self):
        @singleton
        class First:
            pass

        @singleton
        class Second:
            pass

        assert First() is not Second()
        assert First() is First()
        assert Second() is Second()

    def test_instance_state_is_shared(self, decorated_class):
        instance = decorated_class()
        instance.value = "mutated"

        assert decorated_class().value == "mutated"

    def test_propagates_constructor_errors(self):
        @singleton
        class Broken:
            def __init__(self):
                raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            Broken()

    def test_failed_construction_is_not_cached(self):
        attempts = []

        @singleton
        class Flaky:
            def __init__(self):
                attempts.append(1)
                if len(attempts) == 1:
                    raise RuntimeError("first attempt fails")

        with pytest.raises(RuntimeError):
            Flaky()

        instance = Flaky()

        assert len(attempts) == 2
        assert Flaky() is instance

    def test_uses_a_lock_when_creating_the_instance(self, mocker):
        mock_lock = mocker.MagicMock()
        mocker.patch(
            "data_agent.utils.singleton.threading.Lock", return_value=mock_lock
        )

        @singleton
        class Service:
            pass

        Service()

        mock_lock.__enter__.assert_called_once()
        mock_lock.__exit__.assert_called_once()

    def test_lock_is_not_acquired_after_instance_exists(self, mocker):
        mock_lock = mocker.MagicMock()
        mocker.patch(
            "data_agent.utils.singleton.threading.Lock", return_value=mock_lock
        )

        @singleton
        class Service:
            pass

        Service()
        mock_lock.reset_mock()
        Service()

        mock_lock.__enter__.assert_not_called()

    def test_concurrent_calls_return_a_single_instance(self):
        created = []

        @singleton
        class Service:
            def __init__(self):
                created.append(self)

        results = []
        barrier = threading.Barrier(8)

        def worker():
            barrier.wait()
            results.append(Service())

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(created) == 1
        assert len(results) == 8
        assert all(result is results[0] for result in results)
