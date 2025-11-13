import uuid
import secrets
from passlib.hash import argon2
from sqlmodel import SQLModel, Field
from sqlalchemy.orm import Session
from .exceptions import MissingRecord

class User(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(unique=True)
    password: str


    @classmethod
    def delete_by_id(cls, session: Session, user_id):
        user = session.query(cls).where(User.id == user_id).one_or_none()
        if not user:
            raise MissingRecord("User `{user_id}` not found")
        session.delete(user)

    @classmethod
    def delete_by_name(cls, session: Session, name: str):
        user = session.query(cls).where(User.name == name).one_or_none()
        if not user:
            raise MissingRecord("User `{name}` not found")
        session.delete(user)
        
    @classmethod
    def get_by_id(cls, session: Session, user_id):
        user = session.query(cls).where(User.id == user_id).one_or_none()
        if not user:
            raise MissingRecord("User `{user_id}` not found")
        return user
    
    @classmethod
    def get_by_name(cls, session: Session, name: str):
        user = session.query(cls).where(User.name == name).one_or_none()
        if not user:
            raise MissingRecord("User `{name}` not found")
        return user

    @classmethod
    def create(cls, session: Session, name: str) -> str:
        password = secrets.token_urlsafe(128)
        user = User(
            name=name,
            password=argon2.using(rounds=4, memory_cost=65536).hash(password)
        )
        session.add(user)
        return password

    def create_new_password(self, session: Session):
        password = secrets.token_urlsafe(128)
        self.password = password
        session.add(self)
        return password
