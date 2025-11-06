from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
import logging


from .models.exceptions import MissingRecord

from .k8s import load_kube_config
from .models import db
from .api import events, jobs, status
from .ui import router as ui
from .manager import manager


logger = logging.getLogger("uvicorn.error")

app = FastAPI(lifespan=lambda app: lifespan(app))
app.include_router(status.router, prefix="/status")
app.include_router(events.router, prefix="/api/v1/events")
app.include_router(jobs.router, prefix="/api/v1/jobs")
app.include_router(ui.router, prefix="/ui")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    db.init_db()
    logger.info("Loading k8s config...")
    load_kube_config()
    logger.info("Starting manager...")
    manager.start()
    yield
    await manager.stop()


@app.exception_handler(MissingRecord)
async def handle_model_exception(request, exc):
    raise HTTPException(status_code=404, detail=str(exc))

@app.exception_handler(ValueError)
async def handle_value_exception(request, exc):
    raise HTTPException(status_code=400, detail=str(exc))
