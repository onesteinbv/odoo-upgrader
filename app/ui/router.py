from pathlib import Path
import uuid
from fastapi.staticfiles import StaticFiles
import jinja2
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from starlette.status import HTTP_403_FORBIDDEN, HTTP_404_NOT_FOUND

from ..security import user_auth, admin_auth

from ..models.db import Session
from ..models.job import Job
from ..settings import settings


router = APIRouter(include_in_schema=False)


def _render(template_name: str, **context):
    template_dir = Path("app/ui/static")
    template_loader = jinja2.FileSystemLoader(searchpath=template_dir)
    template_env = jinja2.Environment(loader=template_loader)
    template = template_env.get_template(template_name)
    return template.render(**context)


@router.get("/admin", response_class=HTMLResponse, dependencies=[Depends(user_auth)])
async def admin():
    return _render("admin.html.jinja")


@router.get("/logs/{job_id}", response_class=HTMLResponse)
async def logs(job_id: str, user_id: uuid.UUID | None = Depends(admin_auth)):
    with Session() as session:
        job = Job.get_by_id(session, job_id)
    if user_id and job.user_id != user_id:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN)
    return _render("logs.html.jinja", job=job)


@router.get("/upgrade/{upgrade_path}", response_class=HTMLResponse, dependencies=[Depends(user_auth)])
async def upgrade(upgrade_path: str):
    if not settings.upgrade_path_exists(upgrade_path, False):
        raise HTTPException(status_code=404, detail="Upgrade path not found") 
    return _render("upgrade.html.jinja", upgrade_path=upgrade_path)


@router.get("/status/{job_id}", response_class=HTMLResponse)
async def status(job_id: str, user_id: uuid.UUID | None = Depends(user_auth)):
    with Session() as session:
        job = Job.get_by_id(session, job_id)
    if user_id and job.user_id != user_id:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN)
    return _render("status.html.jinja", job=job)