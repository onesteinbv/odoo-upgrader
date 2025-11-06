from pathlib import Path
from fastapi.staticfiles import StaticFiles
import jinja2
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

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


@router.get("/admin", response_class=HTMLResponse)
async def admin():
    return _render("admin.html.jinja")


@router.get("/logs/{job_id}", response_class=HTMLResponse)
async def logs(job_id: str):
    with Session() as session:
        job = Job.get_by_id(session, job_id)
    return _render("logs.html.jinja", job=job)


@router.get("/upgrade/{upgrade_path}", response_class=HTMLResponse)
async def upgrade(upgrade_path: str):
    if not settings.upgrade_path_exists(upgrade_path, False):
        raise HTTPException(status_code=404, detail="Upgrade path not found") 
    return _render("upgrade.html.jinja", upgrade_path=upgrade_path)


@router.get("/status/{job_id}", response_class=HTMLResponse)
async def status(job_id: str):
    with Session() as session:
        job = Job.get_by_id(session, job_id)
    return _render("status.html.jinja", job=job)