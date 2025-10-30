
import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse

from app import k8s
from ..security import get_api_key

from ..manager import Manager, manager


router = APIRouter(dependencies=[Depends(get_api_key)])


@router.post("/")
async def create(
    upgrade_path: str, 
    dump_file: UploadFile | None = File(None),
    args: dict[str, str] | str | None = None,
):
    if isinstance(args, str):  # There should be a better way to do this with FastAPI
        try:
            args = json.loads(args)
        except json.JSONDecodeError:
            raise RequestValidationError("Invalid JSON for args parameter")
        
        if not isinstance(args, dict):
            raise RequestValidationError("Args must be a dict")
            
        for v in args.values():
            if not isinstance(v, str):
                raise RequestValidationError("All args values must be strings")

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
        "suspended": job.suspended,
        "annotations": job.annotations
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
