
import json

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import StreamingResponse

from app import k8s, s3
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
    return [job.to_dto() for job in jobs]


@router.get("/{job_id}")
def get_job(job_id: str):
    job = Manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job.to_dto()


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


@router.get("/{job_id}/{step_id}/download/{artifact}")
async def download_artifact(job_id, step_id, artifact):
    job = Manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    step = list(filter(lambda s: s.id == step_id, job.steps))
    if not step:
        raise HTTPException(status_code=404, detail="Step not found")
    step = step[0]
    if artifact not in step.artifacts:
        raise HTTPException(status_code=404, detail="Artifact not found") 

    paths = step.artifacts[artifact].split("/")

    stream = s3.get(paths[0], "/".join(paths[1:]))
    return StreamingResponse(
        stream,
        media_type="application/octet-stream",
        headers={"Content-Disposition": "attachment; filename=\"%s\"" % paths[-1]}
    ) 
