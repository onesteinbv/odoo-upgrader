import asyncio
from datetime import datetime, UTC
from typing import Dict, Optional, Self
import uuid
from sqlalchemy import Column, asc, delete
from sqlmodel import SQLModel, Field, JSON
from sqlalchemy.orm import Session


class Event(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    creation_date: datetime = Field(
        default_factory=lambda: datetime.now(UTC)
    )
    key: str
    data: Dict = Field(default_factory=dict, sa_column=Column(JSON))

    @classmethod
    def put(cls, session: Session, key: str, data: dict):
        event = Event(key=key, data=data)
        session.add(event)

    @classmethod
    def pop(cls, session: Session) -> Self | None:
        event = session.query(cls).order_by(asc(cls.creation_date)).limit(1).one_or_none()
        if event:
            session.delete(event)
            return event
        return None

    @classmethod
    def truncate(cls, session: Session):
        delete_statement = delete(cls)
        session.execute(delete_statement)
