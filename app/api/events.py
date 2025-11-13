import asyncio
import logging
import json
from contextlib import asynccontextmanager
from typing import List
import uuid
from fastapi import APIRouter, FastAPI, Request, Depends
from sse_starlette import EventSourceResponse as EventSourceResponseBase

from ..security import user_auth

from ..models.event import Event
from ..models.db import Session


logger = logging.getLogger("uvicorn.error")

subscribers: List[asyncio.Queue] = []
lock: asyncio.Lock = asyncio.Lock()


class EventSourceResponse(EventSourceResponseBase):
    def __init__(self, queue: asyncio.Queue, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.queue = queue

    async def __call__(self, *args, **kwargs):
        await super().__call__(*args, **kwargs)
        async with lock:
            subscribers.remove(self.queue)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_poll())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        logger.warning("Polling task cancelled. Exiting.")


router = APIRouter(
    lifespan=lambda app: lifespan(app)
)


@router.get("/")
async def feed(request: Request, user_id: uuid.UUID | None = Depends(user_auth)):
    queue: asyncio.Queue = asyncio.Queue[dict]()
    async with lock:
        subscribers.append(queue)

    async def _generator():
        while not await request.is_disconnected():
            try:
                event = await queue.get()
                event_user_id = event.pop("user_id", None)
                if user_id and event_user_id and event_user_id != user_id:
                    queue.task_done()
                    continue
            except asyncio.CancelledError:
                break
            yield event
            queue.task_done()
    return EventSourceResponse(queue, _generator())

    
async def _broadcast(data: str, event: str = None, user_id: uuid.UUID | None = None):
    async with lock:
        for subscriber in subscribers:
            await subscriber.put(dict(data=json.dumps(data), event=event, user_id=user_id))

async def _poll():
    while True:
        try:
            with Session.begin() as session:
                event = Event.pop(session)
                if event:
                    await _broadcast(event.data, event.key, event.user_id)
                else:
                    await asyncio.sleep(.1)
        except asyncio.CancelledError:
            logger.warning("Polling stopped.")
            break
        except Exception as e:
            logger.error("Error in polling: %s", e)
