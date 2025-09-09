
from sqlmodel import create_engine, SQLModel
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession as BaseAsyncSession

engine = create_engine(
    "sqlite:///app.db"
)

def init_db():
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)

Session = sessionmaker(engine)
AsyncSession = sessionmaker(
    engine, class_=BaseAsyncSession
)
