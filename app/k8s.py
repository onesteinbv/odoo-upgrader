import asyncio
from contextlib import contextmanager, asynccontextmanager, suppress
import os
from pathlib import Path
import shutil
import tempfile
import logging
import time
from typing import AsyncGenerator, Callable, Dict, List, Self
from fastapi import Request
from jinja2 import Template
from kubernetes import config, client, watch
from pydantic import BaseModel

from .settings import S3Settings, settings, StepSettings
from .models.job import Job

FINALIZER = "odoo-upgrader/cleanup"


logger = logging.getLogger("uvicorn.error")


class Context(BaseModel):
    namespace: str
    job_domain: str
    job: Job
    steps: List[StepSettings]
    secret_env: Dict[str, str] = {}
    env: Dict[str, str] = {}
    s3: S3Settings
    args: dict[str, str] = {}

    @staticmethod
    def from_job(job: Job) -> Self:
        upgrade_path = settings.get_upgrade_path(job.upgrade_path)
        secret_env = settings.job_secret_env
        env = {**settings.job_env, **upgrade_path.job_env}
        secret_env = {**settings.job_secret_env, **upgrade_path.job_secret_env}
        args = job.args or {}  # Shortcut

        return Context(
            namespace=settings.job_namespace,
            job_domain=settings.job_domain,
            job=job,
            steps=upgrade_path.steps,
            env=env,
            secret_env=secret_env,
            s3=settings.s3,
            args=args
        )



def load_kube_config():
    if "KUBECONFIG" in os.environ:  # Load from kubeconfig file
        config.load_kube_config(
            os.environ.get("KUBECONFIG")
        )
    else:
        config.load_incluster_config()

def raw(var):
    return "{{ %s }}" % var
    
@contextmanager
def render(manifests_dir: Path, vars: Context):
    manifests_dir = Path(__file__).parent / manifests_dir
    
    with tempfile.TemporaryDirectory() as tmp_dir:
        shutil.copytree(manifests_dir, tmp_dir, dirs_exist_ok=True)
        for file in os.listdir(tmp_dir):
            if not file.endswith(".jinja"):
                continue
            kustomization_tmpl_file = tmp_dir / Path(file)
            kustomization_tmpl = Template(kustomization_tmpl_file.read_text())
            render_context = {**vars.model_dump(), "raw": raw}
            kustomization_render = kustomization_tmpl.render(render_context)
            kustomization_file = tmp_dir / Path(file.replace(".jinja", ""))
            kustomization_file.write_text(kustomization_render)
        yield tmp_dir

async def _kubectl(*args: list[str]) -> str | None:
    logger.debug("Running kubectl with args: %s", args)
    proc = await asyncio.create_subprocess_exec(
        "kubectl", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await proc.communicate()
    if stderr:
        raise Exception(stderr.decode())
    return stdout.decode()

async def apply(manifests_dir: Path, vars: Context):
    with render(manifests_dir, vars) as tmp_dir:
        await _kubectl("apply", "--dry-run=server", "-k", str(tmp_dir))
        await _kubectl("apply", "--wait=false", "-k", str(tmp_dir))

async def delete(manifests_dir: Path, vars: Context):
    with render(manifests_dir, vars) as tmp_dir:
        await _kubectl("delete", "-f", str(tmp_dir), "-n", settings.job_namespace, "--wait=false", "--ignore-not-found=true")

async def delete_all(job_id: str):
    await delete_by_label("odoo-upgrader/src-id", job_id)

async def delete_by_label(label: str, value: str):
    await _kubectl(
        "delete", "job,pvc,configmap,deployment,secret,workflow",
        "--ignore-not-found=true", 
        "--wait=false",
        "-l", "%s=%s" % (label, value),
        "-n", settings.job_namespace,
    )

async def _delete_resource(kind: str, name: str):
    await _kubectl(
        "delete",
        "%s/%s" % (kind, name),
        "-n", settings.job_namespace,
        "--ignore-not-found=true", 
        "--wait=false",
    )

async def delete_workflow(job_id: str):
    await _delete_resource("workflow", job_id)

def set_cleanup_state(job_id: str, state: str):
    _patch_workflow(
        job_id, {
            "metadata": {
                "annotations": {
                    "odoo-upgrader/cleanup-state": state
                }
            }
        }
    )

def remove_finalizer(job_id: str):
    _patch_workflow(
        job_id, {
            "metadata": {
                "finalizers": None
            }
        }
    )

def _patch_workflow(job_id: str, patch: dict):
    custom_objects = client.CustomObjectsApi()
    custom_objects.patch_namespaced_custom_object(
        group="argoproj.io",
        version="v1alpha1",
        namespace=settings.job_namespace,
        plural="workflows",
        name=job_id,
        body=patch
    )

async def logs(step_id: str):
    v1 = client.CoreV1Api()
    pods = v1.list_namespaced_pod(namespace=settings.job_namespace)

    matching_pods = [
        pod for pod in pods.items
        if pod.metadata.annotations and pod.metadata.annotations.get("workflows.argoproj.io/node-id") == step_id
    ]
    if not matching_pods:
        yield "No matching pod found\n"
        return

    pod_name = matching_pods[0].metadata.name
    w = watch.Watch()

    while True:
        try:
            stream = w.stream(
                v1.read_namespaced_pod_log,
                name=pod_name,
                namespace=settings.job_namespace,
                follow=True,
                container="main"
            )
            while True:
                try: 
                    log_lines = await asyncio.to_thread(next, stream)
                    yield log_lines + "\n"
                except StopIteration:
                    break
        except client.ApiException:
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
        except asyncio.CancelledError:
            break
