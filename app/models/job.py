from enum import Enum
import json
from typing import Iterable, List, Self
import uuid

from datetime import datetime, UTC
from pydantic import BaseModel
from sqlalchemy import JSON, Column, TypeDecorator
from sqlmodel import SQLModel, Field
from sqlalchemy.orm import Session

from .exceptions import MissingRecord
from .event import Event


class State(str, Enum):
    pending = "pending"
    dispatched = "dispatched"
    in_progress = "in_progress"
    failed = "failed"
    succeeded = "succeeded"
    skipped = "skipped"

    suspended = "suspended"
    awaiting = "awaiting"

    cleanup_pending = "cleanup_pending"
    cleanup_dispatched = "cleanup_dispatched"
    cleanup_started = "cleanup_started"
    cleanup_finished = "cleanup_finished"
    cleanup_failed = "cleanup_failed"

    @staticmethod
    def from_k8s_phase(phase: str):
        if phase == "Pending":
            return State.dispatched
        elif phase == "Running":
            return State.in_progress
        elif phase == "Failed":
            return State.failed
        elif phase == "Error":
            return State.failed
        elif phase == "Succeeded":
            return State.succeeded
        elif phase == "Skipped":
            return State.skipped
        else:
            raise ValueError("Unknown job state: %s" % phase)
        
    @staticmethod 
    def from_cleanup_state_annotation(value: str):
        if value == "pending":
            return State.cleanup_dispatched
        elif value == "started":
            return State.cleanup_started
        elif value == "finished":
            return State.cleanup_finished
        elif value == "failed":
            return State.cleanup_failed
        else:
            raise ValueError("Unknown cleanup state: %s" % value)


class Step(BaseModel):
    name: str
    id: str
    state: State
    message: str | None = None
    finished_at: float | None = None
    started_at: float | None = None
    args: dict[str, str] = {}


class StepListDecorator(TypeDecorator):
    impl = JSON

    def process_bind_param(self, value: List[Step], dialect):
        if value is None:
            return None
        return json.dumps([item.model_dump() for item in value])

    def process_result_value(self, value: str, dialect):
        if value is None:
            return None
        data = json.loads(value)
        return [Step(**item) for item in data]


class Job(SQLModel, table=True):
    # Not directly a UUID field as resubmitting workflows in argo will generate a randomized name for the new workflow that is not a UUID (e.g. 5cc25da5-82f5-46e0-b6cc-ed7ee8d30507-7rgq8)
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    creation_date: datetime = Field(
        default_factory=lambda: datetime.now(UTC)
    )
    updated_date: datetime | None = Field(default=None)
    state: State = Field(default=State.pending)

    dump_object: str | None
    upgrade_path: str | None
    steps: List[Step] = Field(default_factory=list, sa_column=Column(StepListDecorator))
    src_id: str | None
    args: dict[str, str] | None = Field(sa_type=JSON)

    @property
    def progress(self) -> float:
        if not self.steps:
            return 0.0
        completed_steps = len(list(filter(lambda s: s.state in {State.succeeded, State.failed}, self.steps)))
        return completed_steps / len(self.steps)
    
    @property
    def suspended(self) -> bool:
        return (
            bool(list(filter(lambda s: s.state == State.suspended, self.steps)))
        )
    @property
    def awaiting(self) -> bool:
        return (
            bool(list(filter(lambda s: s.state == State.awaiting, self.steps)))
        )
    
    @classmethod
    def get_all(cls, session: Session) -> List[Self]:
        return session.query(cls).all()

    @classmethod
    def get_by_id(cls, session: Session, job_id: str, raise_exception=True) -> Self | None:
        record = session.get(cls, job_id)
        if not record and raise_exception:
            raise MissingRecord("Record with id `%s` not found" % job_id)
        return record

    @classmethod
    def get_by_src_id(cls, session: Session, job_id: str):
        return session.query(cls).filter(cls.src_id == job_id).all()
    
    @classmethod
    def get_by_state(cls, session: Session, state: State):
        return session.query(cls).filter(cls.state == state).all()
    
    @classmethod
    def get_by_states(cls, session: Session, states: Iterable[State]) -> List[Self]:
        return session.query(cls).filter(cls.state.in_(states)).all()

    @classmethod
    def from_k8s_object(cls, k8s_object: dict) -> Self:
        # Shortcuts
        metadata = k8s_object["metadata"]
        labels = metadata.get("labels", {})
        annotations = metadata.get("annotations", {})
        status = k8s_object["status"]

        # Parse nodes
        steps: List[Step] = []
        if status.get("nodes"):
            pod_workflow_nodes = filter(lambda n: n["type"] in ("Pod", "Suspend"), status["nodes"].values())
            for node in pod_workflow_nodes:
                finished_at = None
                if node.get("finishedAt"):
                    finished_at = datetime.strptime(node["finishedAt"], "%Y-%m-%dT%H:%M:%SZ")
                    finished_at = finished_at.timestamp()

                started_at = None
                if node.get("startedAt"):
                    started_at = datetime.strptime(node["startedAt"], "%Y-%m-%dT%H:%M:%SZ")
                    started_at = started_at.timestamp()      

                state = State.from_k8s_phase(node["phase"])
                args = {}
                if node.get("inputs") and node["inputs"].get("parameters"):
                    args = {param["name"]: param["value"] for param in node["inputs"]["parameters"]}
                
                # Use a seperate state for in_progress for suspend nodes for convencience
                if state == State.in_progress and node["type"] == "Suspend":
                    state = not args and State.suspended or State.awaiting

                step = Step(
                    id=node["id"],
                    name=node["displayName"],
                    state=state,
                    message=node.get("message", None),
                    finished_at=finished_at,
                    started_at=started_at,
                    args=args
                )
                steps.append(step)
        steps.sort(key=lambda x: x.started_at)  # Sort here for convenience
        job_state = State.from_k8s_phase(status["phase"])
        if annotations.get("odoo-upgrader/cleanup-state"):
            job_state = State.from_cleanup_state_annotation(
                annotations["odoo-upgrader/cleanup-state"]
            )
        
        job_id = metadata["name"]
        return cls(
            id=job_id,
            src_id=labels["odoo-upgrader/src-id"],
            creation_date=datetime.strptime(metadata["creationTimestamp"], "%Y-%m-%dT%H:%M:%SZ"),
            state=job_state,
            dump_object=annotations["odoo-upgrader/dump-object"],
            upgrade_path=annotations["odoo-upgrader/upgrade-path"],
            steps=steps
        )
