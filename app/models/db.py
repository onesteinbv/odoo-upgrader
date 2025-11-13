
from sqlmodel import create_engine, SQLModel
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession as BaseAsyncSession

from .job import Job
from .event import Event

engine = create_engine(
    "sqlite:///app.db"
)

Session = sessionmaker(engine)
AsyncSession = sessionmaker(
    engine, class_=BaseAsyncSession
)

def init_db():
    SQLModel.metadata.create_all(engine)

    # Truncate jobs, events
    with Session.begin() as session:
        Job.truncate(session)
        Event.truncate(session)
        session.commit()
