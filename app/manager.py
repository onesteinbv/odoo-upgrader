import asyncio
import logging
from pathlib import Path
import uuid
from kubernetes import watch, client
from kubernetes.client.exceptions import ApiException
from sqlmodel import select
import urllib3
from urllib3.exceptions import ReadTimeoutError

from .models.db import Session
from .models.job import Job, State
from .models.event import Event
from .settings import settings
from . import k8s
from . import s3
from . import argo


logger = logging.getLogger("uvicorn.error")

class Manager:
    def __init__(self) -> None:
        self._watch = watch.Watch()
        self._watch_task: asyncio.Task = None
        self._dispatcher_task: asyncio.Task = None
        self._dispatcher_event: asyncio.Event = asyncio.Event()
        self._cleaner_task: asyncio.Task = None
        self._cleaner_event: asyncio.Event = asyncio.Event()

    def start(self):
        self._watch_task = asyncio.create_task(
            self._watch_workflows()
        )
        self._dispatcher_task = asyncio.create_task(
            self._dispatcher()
        )
        self._cleaner_task = asyncio.create_task(
            self._cleaner()
        )
        self._load()

    async def stop(self):
        self._watch_task.cancel()
        self._dispatcher_task.cancel()
        self._cleaner_task.cancel()
        try:
            await asyncio.gather(self._watch_task, self._dispatcher_task, self._cleaner_task)
        except asyncio.CancelledError:
            logger.warning("Tasks cancelled. Exiting.")        

    def _load(self):
        logger.info("Loading existing jobs...")
        custom_objects = client.CustomObjectsApi()
        workflow_list = custom_objects.list_namespaced_custom_object(
            group="argoproj.io",
            version="v1alpha1",
            plural="workflows",
            namespace=settings.job_namespace
        )
        workflows = workflow_list["items"]
        jobs_awaiting = False
        for workflow in workflows:
            managed_by = workflow["metadata"]["labels"].get("app.kubernetes.io/managed-by")
            if managed_by != "odoo-upgrader":
                continue
            job_type = workflow["metadata"]["labels"]["odoo-upgrader/type"]
            if job_type != "upgrade":
                continue
            job: Job = Job.from_k8s_object(workflow)
            with Session.begin() as session:
                session.add(job)
                if job.awaiting:
                    jobs_awaiting = True
        if jobs_awaiting:  # Can be moved to _on_upgrade_workflow_event
            self._dispatcher_event.set()

    async def _watch_workflows(self):
        custom_objects = client.CustomObjectsApi()
        list_method = custom_objects.list_namespaced_custom_object
        w = watch.Watch()

        def _watch():
            try:
                workflow_list = list_method(
                    group="argoproj.io",
                    version="v1alpha1",
                    plural="workflows",
                    namespace=settings.job_namespace
                )
                resource_version = workflow_list["metadata"]["resourceVersion"]

                for event in w.stream(
                    list_method,
                    group="argoproj.io",
                    version="v1alpha1",
                    plural="workflows",
                    namespace=settings.job_namespace,
                    resource_version=resource_version
                ):
                    logger.debug("Received event: %s", event)
                    self._on_workflow_event(event)
            except (ReadTimeoutError, urllib3.exceptions.ProtocolError) as e:
                logger.debug("Timeout watching workflows: %s", e)
            except urllib3.exceptions.MaxRetryError as e:
                logger.error("Error watching workflows: %s", e)
            except ApiException as e:
                if e.status != 410: # Resource version too old
                    logger.error("Unexpected error watching workflows: %s", e)
            except Exception as e:
                logger.error("Unexpected error watching workflows: %s", e)

        while True:
            try:
                await asyncio.to_thread(_watch)
            except asyncio.CancelledError:
                logger.warning("Workflow watcher cancelled.")
                break
            

    def _on_workflow_event(self, event):
        workflow = event["object"]
        managed_by = workflow["metadata"]["labels"].get("app.kubernetes.io/managed-by")
        if managed_by != "odoo-upgrader":
            logger.debug("Workflow not managed by odoo-upgrader: %s", workflow)
            return

        job_type = workflow["metadata"]["labels"]["odoo-upgrader/type"]
        if job_type == "upgrade":
            self._on_upgrade_workflow_event(event)
        elif job_type == "cleanup":
            self._on_cleanup_workflow_event(event)
        else:
            logger.error("Workflow type `%s` not implemented", job_type)

    def _on_upgrade_workflow_event(self, event):
        workflow = event["object"]
        event_type = event["type"]
        job_id = workflow["metadata"]["name"]
        status = workflow.get("status")

        if not status:
            return
        
        if event_type == "DELETED":
            return

        job_awaiting = False
        with Session.begin() as session:
            job = Job.get_by_id(session, job_id, False)
            if job:
                previous_state = job.state
                job.sqlmodel_update(Job.from_k8s_object(workflow))
                job_state = job.state
                session.add(job)
                Event.put(session, "job:updated", {
                    "id": str(job.id),
                    "state": job.state,
                    "steps": [step.to_dto() for step in job.steps],
                    "progress": job.progress,
                    "suspended": job.suspended,
                    "annotations": job.annotations
                }, job.user_id)
                job_awaiting = job.awaiting
            else:
                previous_state = State.pending
                job = Job.from_k8s_object(workflow)
                job_state = job.state
                session.add(job)
                Event.put(session, "job:new", {
                    "id": str(job.id),
                    "src_id": str(job.src_id),
                    "state": job.state,
                    "steps": [step.to_dto() for step in job.steps],
                    "progress": job.progress,
                    "suspended": job.suspended,
                    "annotations": job.annotations
                }, job.user_id)

        if job_awaiting:
            self._dispatcher_event.set()

        if previous_state == job_state:
            return
    
        if job_state == State.in_progress:
            logger.info("Job `%s` is running", job_id)
        elif job_state == State.succeeded:
            logger.info("Job `%s` succeeded", job_id)
        elif job_state == State.failed:
            logger.error("Job `%s` failed", job_id)
        elif job_state == State.cleanup_failed:
            logger.error("Cleanup of job `%s` failed", job_id)
        elif job_state == State.cleanup_finished:
            logger.info("Cleanup of job `%s` finished", job_id)
            self._cleaner_event.set()
        elif job_state == State.cleanup_started:
            logger.info("Cleanup of job `%s` started", job_id)

    def _on_cleanup_workflow_event(self, event):
        workflow = event["object"]
        job_id = workflow["metadata"]["labels"]["odoo-upgrader/job-id"]
        status = workflow.get("status")
        if not status:
            return
        
        workflow_state = State.from_k8s_phase(status["phase"])
        with Session.begin() as session:
            job = Job.get_by_id(session, job_id, False)
            if not job:
                return
            previous_state = \
                job.state == State.cleanup_failed and State.failed or \
                job.state == State.cleanup_started and State.in_progress or \
                job.state == State.cleanup_finished and State.succeeded

        if previous_state == workflow_state:
            return
        
        if workflow_state == State.in_progress:
            k8s.set_cleanup_state(job_id, "started")
        elif workflow_state == State.succeeded:
            k8s.set_cleanup_state(job_id, "finished")
        elif workflow_state == State.failed:
            k8s.set_cleanup_state(job_id, "failed")

    async def _dispatcher(self):
        while True:
            await self._dispatcher_event.wait()
            self._dispatcher_event.clear()
            with Session() as session:
                pending_jobs = Job.get_by_state(session, State.pending)
                awaiting_jobs = list(filter(lambda j: j.awaiting, Job.get_by_state(session, State.in_progress)))
                if not pending_jobs and not awaiting_jobs:
                    logger.warning("_dispatcher_event triggered unnecessary")
            for job in pending_jobs:
                upgrade_path = settings.get_upgrade_path(job.upgrade_path)
                try:
                    await k8s.apply(
                        upgrade_path.manifest_dir, 
                        k8s.Context.from_job(job)
                    )
                    logger.info("Job deployed `%s`" % job.id)
                    with Session.begin() as session:
                        job.state = State.dispatched
                        session.add(job)
                        Event.put(session, "job:updated", {
                            "id": str(job.id),
                            "state": job.state
                        }, job.user_id)
                except Exception as e:
                    logger.error("Failed to deploy job `%s`: %s", job.id, e)
                    with Session.begin() as session:
                        job.state = State.failed
                        session.add(job)
                        Event.put(session, "job:updated", {
                            "id": str(job.id),
                            "state": job.state
                        }, job.user_id)
            for job in awaiting_jobs:
                try:
                    last_step = job.steps[-1]
                    command = last_step.args["command"]
                    command_args = {**last_step.args}
                    command_args.pop("command")
                    await self._execute_command(job.id, command, command_args)
                except Exception as e:
                    logger.error("Job failed `%s`: %s", job.id, e)
                    await argo.terminate(job.id)
                    with Session.begin() as session:
                        job.state = State.failed
                        session.add(job)
                        Event.put(session, "job:updated", {
                            "id": str(job.id),
                            "state": job.state
                        }, job.user_id)
    
    async def _cleaner(self):
        while True:
            await self._cleaner_event.wait()
            self._cleaner_event.clear()
            with Session() as session:
                pending_jobs = Job.get_by_state(session, State.cleanup_pending)
                finished_jobs = Job.get_by_state(session, State.cleanup_finished)

            for job in pending_jobs:  # Dispatch clean workflows
                upgrade_path = settings.get_upgrade_path(job.upgrade_path)
                try:
                    await k8s.apply(
                        upgrade_path.manifest_dir / "cleanup", 
                        k8s.Context.from_job(job)
                    )
                    logger.info("Job cleanup dispatched `%s`" % job.id)
                    with Session.begin() as session:
                        job.state = State.cleanup_dispatched
                        session.add(job)
                        Event.put(session, "job:updated", {
                            "id": str(job.id),
                            "state": job.state
                        }, job.user_id)
                except Exception as e:
                    logger.error("Failed to cleanup job `%s`: %s", job.id, e)
                    with Session.begin() as session:
                        job.state = State.cleanup_failed
                        session.add(job)
                        Event.put(session, "job:updated", {
                            "id": str(job.id),
                            "state": job.state
                        }, job.user_id)
    
            for job in finished_jobs:  # Garbage collect jobs
                await k8s.delete_workflow(job.id)
                with Session.begin() as session:
                    delete_resources = len(Job.get_by_src_id(session, job.src_id)) == 1
                    session.delete(job)
                    Event.put(session, "job:deleted", {
                        "id": str(job.id)
                    }, job.user_id)
                if delete_resources:  # Keep resources for potential resubmission
                    if job.s3_object:
                        await s3.delete(job.s3_object)
                    await k8s.delete_all(job.src_id)

    async def new_job(
            self, 
            upgrade_path: str, 
            file: bytes | None = None,
            user_id: uuid.UUID | None = None,
            args: dict[str, str] | None = None
        ) -> str:
        # Check whether a file is required for this upgrade path
        upgrade_path_settings = settings.get_upgrade_path(upgrade_path)
        if not file and upgrade_path_settings.requires_file:
            raise ValueError("File is required for this upgrade path.")

        # Upload dump to s3
        object_key = None
        if file:
            object_key = str(uuid.uuid4())
            await s3.upload(object_key, file)

        # Create a job record and put an event out
        job = Job(upgrade_path=upgrade_path, s3_object=object_key, user_id=user_id, args=args)
        job.src_id = job.id
        res = None
        with Session.begin() as session:
            session.add(job)
            Event.put(session, "job:new", {
                "id": str(job.id),
                "state": job.state
            }, job.user_id)
            res = job.id

        # Signal the dispatcher to process new jobs
        self._dispatcher_event.set()
        return res
    
    async def delete_job(self, job_id: str):
        with Session.begin() as session:
            job = Job.get_by_id(session, job_id)
            if job.state in {State.cleanup_pending, State.cleanup_started, State.cleanup_dispatched}:
                raise Exception("Cleanup already started for `%s`" % job_id)
            if job.state in {State.cleanup_failed, State.cleanup_finished}:
                await k8s.delete_by_label("odoo-upgrader/job-id", job_id)
            if job.state in {State.pending, State.in_progress}:
                await argo.terminate(job_id)
            job.state = State.cleanup_pending
            session.add(job)
        self._cleaner_event.set()

    async def delete_all(self):
        with Session.begin() as session:
            jobs = Job.get_by_states(
                session, 
                (
                    State.cleanup_failed, 
                    State.cleanup_finished, 
                    State.pending, 
                    State.in_progress, 
                    State.succeeded, 
                    State.failed,
                    State.suspended,
                    State.awaiting
                )
            )
            awaitables = []
            for job in jobs:
                if job.state in {State.cleanup_failed, State.cleanup_finished}:
                    awaitables.append(k8s.delete_by_label("odoo-upgrader/job-id", job.id))
                if job.state in {State.pending, State.in_progress}:
                    awaitables.append(argo.terminate(job.id))
            await asyncio.gather(*awaitables)
            for job in jobs:
                job.state = State.cleanup_pending
                session.add(job)
        self._cleaner_event.set()


    async def _execute_command(self, job_id: str, command: str, kwargs: dict[str, str]):
        logger.info("Execute command `%s` for `%s`", command, job_id)
        func = getattr(self, "_command_%s" % command)
        try:
            await func(job_id, **kwargs)
            await argo.resume(job_id)
        except Exception as e:
            logger.error("Job failed `%s`: %s", job_id, e)
            await argo.terminate(job_id)
            with Session.begin() as session:
                job = Job.get_by_id(session, job_id)
                job.state = State.failed
                session.add(job)
                Event.put(session, "job:updated", {
                    "id": str(job.id),
                    "state": job.state
                }, job.user_id)
            return

    async def _command_echo(self, job_id: str, message: str):
        logger.info(message)

    async def _command_deploy(self, job_id: str, manifests_dir: str, **kwargs: dict[str, str]):
        with Session() as session:
            job = Job.get_by_id(session, job_id)
            context: k8s.Context = k8s.Context.from_job(job)
            context.args.update(**kwargs)
        await k8s.apply(manifests_dir, context)
        k8s.append_annotations(job_id, {
            "odoo-upgrader/deployment-url": "https://%s-%s.%s" % (
                job.id,
                context.args["mode"],
                settings.job_domain
            )
        })

    async def _command_undeploy(self, job_id: str, manifests_dir: str, **kwargs: dict[str, str]):
        with Session() as session:
            job = Job.get_by_id(session, job_id)
            context: k8s.Context = k8s.Context.from_job(job)
            context.args.update(**kwargs)
        await k8s.delete(manifests_dir, context)

    @classmethod
    async def resume_job(cls, job_id: str):
        with Session.begin() as session:
            job = Job.get_by_id(session, job_id)
            if not job.suspended:
                raise Exception("Job `{job_id}` is not suspended")
        await argo.resume(job_id)


manager = Manager()
