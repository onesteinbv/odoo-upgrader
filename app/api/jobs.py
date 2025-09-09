
import asyncio
from pathlib import Path
from typing import Optional, Required
from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import StreamingResponse

from app import k8s
from app.models.job import Job

from ..manager import Manager, manager


router = APIRouter()


@router.post("/")
async def create(
    upgrade_path: str, 
    dump_file: UploadFile | None = File(None),
    args: dict[str, str] | None = None,
):
    if dump_file:
        dump_file = dump_file.file.read()

    return await manager.new_job(
        upgrade_path, dump_file, args
    )

@router.delete("/all")
async def delete_all():
    return await manager.delete_all()

@router.delete("/{job_id}")
async def delete(
    job_id: str, 
):
    return await manager.delete_job(job_id)


@router.get("/")
async def get_jobs():
    jobs = Manager.get_jobs()
    return [{
        "id": job.id, 
        "src_id": job.src_id,
        "state": job.state,
        "steps": job.steps,
        "progress": job.progress,
        "suspended": job.suspended
    } for job in jobs]


@router.get("/{step_id}/logs")
async def logs(
    step_id: str
) -> StreamingResponse:
    return StreamingResponse(k8s.logs(step_id))    


@router.post("/{job_id}/resume")
async def resume(
    job_id: str
):
    return await Manager.resume_job(job_id)
