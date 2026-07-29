import importlib

import pytest


@pytest.fixture
def reload_module(mocker):
    """Re-execute a module so its import-time wiring runs against patched symbols.

    The agent modules build their ``Agent`` objects at import time, so the only
    way to observe that wiring is to reload them while the collaborators they
    import are patched. Every reloaded module is restored afterwards -- mocks are
    stopped first so the restoring reload rebinds the real symbols.
    """
    reloaded = []

    def _reload(module):
        reloaded.append(module)
        return importlib.reload(module)

    yield _reload

    mocker.stopall()
    for module in reversed(reloaded):
        importlib.reload(module)
