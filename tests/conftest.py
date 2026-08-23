"""Shared test bootstrap.

The application depends on ``fabrix-adk``, a private package that provides both
``fabrix`` and the ``google.adk`` bundle. It cannot be installed from a public
index, so when it is missing this file registers minimal stand-ins for the names
the application imports. Only third-party modules are stubbed -- every module
under ``data_agent`` and ``common`` is imported from disk as usual.

The stubs exist to make the import graph resolvable. Tests do not rely on their
behaviour: any ADK symbol a test exercises (``Event``, ``EventActions``,
``types``, ``Runner``, ``Agent``, ``build_model``, ...) is replaced with
``mocker.patch`` inside the test module itself. When the real packages are
installed the stubs are skipped and the same tests run unchanged.
"""

import sys
import types
import pathlib

ROOT_DIR = pathlib.Path(__file__).parent.parent

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def _module(name: str, is_package: bool = False) -> types.ModuleType:
    module = types.ModuleType(name)
    if is_package:
        module.__path__ = []
    return module


def _register(modules: dict) -> None:
    """Publish stub modules and wire each one onto its parent as an attribute."""
    sys.modules.update(modules)
    for name, module in modules.items():
        parent_name, _, attribute = name.rpartition(".")
        if parent_name in modules:
            setattr(modules[parent_name], attribute, module)


def _install_adk_stub() -> None:
    """Stand in for the ``google.adk`` / ``google.genai`` names the app imports."""

    class BaseArtifactService:
        pass

    class BaseSessionService:
        pass

    class DatabaseSessionService(BaseSessionService):
        def __init__(self, db_url=None):
            self.db_url = db_url

    class InMemorySessionService(BaseSessionService):
        pass

    class Session:
        pass

    class EventActions:
        def __init__(self, state_delta=None, escalate=False):
            self.state_delta = state_delta
            self.escalate = escalate

    class Event:
        def __init__(self, author=None, actions=None, content=None, timestamp=None, error_message=None):
            self.author = author
            self.actions = actions
            self.content = content
            self.timestamp = timestamp
            self.error_message = error_message

        def is_final_response(self):
            return True

    class Runner:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class Agent:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class AgentTool:
        def __init__(self, agent=None):
            self.agent = agent

    class MCPToolset:
        def __init__(self, connection_params=None, **kwargs):
            self.connection_params = connection_params

    class StreamableHTTPConnectionParams:
        def __init__(self, url=None):
            self.url = url

    class Blob:
        def __init__(self, data=None, mime_type=None):
            self.data = data
            self.mime_type = mime_type

    class Part:
        def __init__(self, text=None, inline_data=None):
            self.text = text
            self.inline_data = inline_data

        @classmethod
        def from_bytes(cls, *, data, mime_type):
            return cls(inline_data=Blob(data=data, mime_type=mime_type))

    class Content:
        def __init__(self, role=None, parts=None):
            self.role = role
            self.parts = parts

    google = _module("google", is_package=True)
    adk = _module("google.adk", is_package=True)

    artifacts = _module("google.adk.artifacts")
    artifacts.BaseArtifactService = BaseArtifactService

    sessions = _module("google.adk.sessions")
    sessions.BaseSessionService = BaseSessionService
    sessions.DatabaseSessionService = DatabaseSessionService
    sessions.InMemorySessionService = InMemorySessionService
    sessions.Session = Session

    events = _module("google.adk.events")
    events.Event = Event
    events.EventActions = EventActions

    runners = _module("google.adk.runners")
    runners.Runner = Runner

    adk_agents = _module("google.adk.agents", is_package=True)
    llm_agent = _module("google.adk.agents.llm_agent")
    llm_agent.Agent = Agent

    tools = _module("google.adk.tools", is_package=True)
    tools.AgentTool = AgentTool
    mcp_tool = _module("google.adk.tools.mcp_tool", is_package=True)
    mcp_toolset = _module("google.adk.tools.mcp_tool.mcp_toolset")
    mcp_toolset.MCPToolset = MCPToolset
    mcp_session_manager = _module("google.adk.tools.mcp_tool.mcp_session_manager")
    mcp_session_manager.StreamableHTTPConnectionParams = StreamableHTTPConnectionParams

    genai = _module("google.genai", is_package=True)
    genai_types = _module("google.genai.types")
    genai_types.Blob = Blob
    genai_types.Part = Part
    genai_types.Content = Content

    _register({
        "google": google,
        "google.adk": adk,
        "google.adk.artifacts": artifacts,
        "google.adk.sessions": sessions,
        "google.adk.events": events,
        "google.adk.runners": runners,
        "google.adk.agents": adk_agents,
        "google.adk.agents.llm_agent": llm_agent,
        "google.adk.tools": tools,
        "google.adk.tools.mcp_tool": mcp_tool,
        "google.adk.tools.mcp_tool.mcp_toolset": mcp_toolset,
        "google.adk.tools.mcp_tool.mcp_session_manager": mcp_session_manager,
        "google.genai": genai,
        "google.genai.types": genai_types,
    })


def _install_fabrix_stub() -> None:
    """Stand in for the ``fabrix.adk`` helpers the agents are built with."""

    class RuntimeApp:
        def __init__(self, runtime_root, app_name=None):
            self.runtime_root = runtime_root
            self.app_name = app_name

    def build_model(model_name_or_id):
        return f"model:{model_name_or_id}"

    def create_runtime_app(runtime_root, app_name=None):
        return RuntimeApp(runtime_root, app_name=app_name)

    fabrix = _module("fabrix", is_package=True)
    adk = _module("fabrix.adk", is_package=True)

    models = _module("fabrix.adk.models")
    models.build_model = build_model

    runtime = _module("fabrix.adk.runtime")
    runtime.create_runtime_app = create_runtime_app
    runtime.RuntimeApp = RuntimeApp

    _register({
        "fabrix": fabrix,
        "fabrix.adk": adk,
        "fabrix.adk.models": models,
        "fabrix.adk.runtime": runtime,
    })


try:
    import google.adk  # noqa: F401
except ImportError:
    _install_adk_stub()

try:
    import fabrix.adk  # noqa: F401
except ImportError:
    _install_fabrix_stub()
