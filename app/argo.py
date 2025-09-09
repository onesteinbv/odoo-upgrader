
import asyncio
import logging
from .settings import settings


logger = logging.getLogger("uvicorn.error")


async def _argo(*args: list[str]) -> str | None:
    logger.debug("Running argo with args: %s", args)
    proc = await asyncio.create_subprocess_exec(
        "argo", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
   
    if stderr:
        stderr = stderr.decode()
        if "level=warning" not in stderr:
            raise Exception(stderr)
    return stdout.decode()

async def resume(workflow: str):
    await _argo("resume", workflow, "-n", settings.job_namespace)

async def stop(workflow: str):
    await _argo("stop", workflow, "-n", settings.job_namespace)

async def terminate(workflow: str):
    await _argo("terminate", workflow, "-n", settings.job_namespace)
