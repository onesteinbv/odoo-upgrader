
import json
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse
from starlette.status import HTTP_403_FORBIDDEN, HTTP_404_NOT_FOUND

from app import k8s, s3
from ..models.job import Job
from ..models.db import Session
from ..security import user_auth, admin_auth

from ..manager import Manager, manager

router = APIRouter()


@router.post("/")
async def create(
    upgrade_path: str, 
    file: UploadFile | None = File(None),
    args: dict[str, str] | str | None = None,
    user_id: uuid.UUID | None = Depends(user_auth)
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

    if file:
        file = file.file.read()

    return await manager.new_job(
        upgrade_path, file, user_id, args
    )


@router.delete("/all", dependencies=[Depends(admin_auth)])
async def delete_all():
    return await manager.delete_all()


@router.delete("/{job_id}")
async def delete(
    job_id: str, 
):
    return await manager.delete_job(job_id)


@router.get("/")
async def get_jobs(user_id: uuid.UUID | None = Depends(user_auth)):
    with Session() as session:
        jobs = Job.get_all(session, user_id)
    return [job.to_dto() for job in jobs]


@router.get("/{job_id}")
def get_job(job_id: str, user_id: uuid.UUID | None = Depends(user_auth)):
    with Session() as session:
        return Job.get_by_id(session, job_id, False)
    if not job:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Job not found")
    if user_id and job.user_id != user_id:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Access denied")
    return job.to_dto()


@router.get("/{job_id}/{step_id}/logs")
async def logs(
    job_id: str,
    step_id: str,
    user_id: uuid.UUID | None = Depends(user_auth)
) -> StreamingResponse:
    with Session() as session:
        job = Job.get_by_id(session, job_id, False)
    if not job:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Job not found")
    if user_id and job.user_id != user_id:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Access denied")
    step = list(filter(lambda s: s.id == step_id, job.steps))
    if not step:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Step not found")

    return StreamingResponse(k8s.logs(step_id))


@router.post("/{job_id}/resume")
async def resume(
    job_id: str, user_id: uuid.UUID | None = Depends(user_auth)
):
    job = Manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Job not found")
    if user_id and job.user_id != user_id:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Access denied")
    return await Manager.resume_job(job_id)


@router.get("/{job_id}/{step_id}/download/{artifact}")
async def download_artifact(job_id, step_id, artifact, user_id: uuid.UUID | None = Depends(user_auth)):
    job = Manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Job not found")
    if user_id and job.user_id != user_id:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Access denied")
    step = list(filter(lambda s: s.id == step_id, job.steps))
    if not step:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Step not found")
    step = step[0]
    if artifact not in step.artifacts:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Artifact not found") 

    paths = step.artifacts[artifact].split("/")

    stream = s3.get(paths[0], "/".join(paths[1:]))
    return StreamingResponse(
        stream,
        media_type="application/octet-stream",
        headers={"Content-Disposition": "attachment; filename=\"%s\"" % paths[-1]}
    ) 
