import asyncio
import time
import logging

from fastapi import UploadFile
from google.adk.events import Event, EventActions
from google.adk.runners import Runner
from google.adk.sessions import BaseSessionService
from google.genai import types

from common.constants import APP_NAME, SYSTEM_AUTHOR
from data_agent.agents import agent_app
from data_agent.schemas import RunAgentRequest, RunAgentResponse
from data_agent.services.db_session import DBSessionService
from data_agent.services.os_artifact import OSArtifactService
from data_agent.services.session_guard import SessionGuard
from data_agent.utils import convert_unix_to_datetime

logger = logging.getLogger(__name__)


class AgentRunner:
    def __init__(
            self,
            session_service: BaseSessionService,
            artifact_service: OSArtifactService,
            db_session_service: DBSessionService,
            session_guard: SessionGuard
    ):
        self._session_service = session_service
        self._artifact_service = artifact_service
        self._db_session_service = db_session_service
        self._session_guard = session_guard
        self._background_tasks: set[asyncio.Task] = set()
        self._app_name = APP_NAME
        self._runner = Runner(
            app=agent_app,
            app_name=APP_NAME,
            session_service=session_service,
            artifact_service=artifact_service
        )

    def _schedule_session_title(self, user_id: str, session_id: str):
        """Title the session in the background, now that the run let go of it.

        The task is kept referenced until it finishes, otherwise the event loop is
        free to garbage collect it mid-flight.
        """
        task = asyncio.create_task(self._db_session_service.ensure_session_title(user_id, session_id))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def run(
            self,
            user_id: str,
            session_id: str,
            request: RunAgentRequest,
            image_file: UploadFile | None = None
    ) -> RunAgentResponse:
        try:
            t1 = time.monotonic()
            logger.info(f"[TIMING] runner START session={session_id} query={request.query!r}")
            parts = []

            # The runner holds the Session it loads for the whole invocation, and any
            # append landing in that window makes the run's own appends stale. Nothing
            # else may write this session until the run is done.
            async with self._session_guard.hold(session_id):
                if image_file is not None:
                    image_bytes = await image_file.read()
                    content_type = image_file.content_type or "image/jpeg"

                    parts.append(types.Part.from_bytes(data=image_bytes, mime_type=content_type))
                    version = await self._artifact_service.save_artifact(
                        app_name=self._app_name,
                        user_id=user_id,
                        session_id=session_id,
                        filename=image_file.filename,
                        artifact=types.Part.from_bytes(data=image_bytes, mime_type=content_type)
                    )
                    key = self._artifact_service.get_object_key(
                        app_name=self._app_name,
                        user_id=user_id,
                        session_id=session_id,
                        filename=image_file.filename,
                        version=version
                    )

                    session = await self._session_service.get_session(
                        app_name=self._app_name,
                        user_id=user_id,
                        session_id=session_id
                    )

                    await self._session_service.append_event(session, Event(
                        author=SYSTEM_AUTHOR,
                        actions=EventActions(state_delta={"pending_image": {
                            "key": key, "filename": image_file.filename, "content_type": content_type
                        }})
                    ))

                parts.append(types.Part(text=request.query))
                content = types.Content(role="user", parts=parts)
                events = self._runner.run_async(user_id=user_id, session_id=session_id, new_message=content)

                response = "No response received."
                timestamp = None
                final_seen = False

                async for event in events:
                    logger.info(f"[TIMING] event author={event.author} type={type(event).__name__} at={time.time()}")
                    if not final_seen and event.is_final_response():
                        final_seen = True
                        timestamp = event.timestamp
                        if event.content and event.content.parts:
                            response = event.content.parts[-1].text
                        elif event.actions and event.actions.escalate:
                            response = f"Agent escalated: {event.error_message or 'No specific message.'}"

            self._schedule_session_title(user_id, session_id)

            logger.info(f"Run agent with request {response}")
            logger.info(f"[TIMING] runner API END session={session_id} elapsed={time.monotonic() - t1:.2f}s")
            return RunAgentResponse(response=response, timestamp=convert_unix_to_datetime(timestamp))
        except Exception as e:
            logger.exception(f"Failed to run agent {session_id} of user {user_id}: {str(e)}")
            raise
