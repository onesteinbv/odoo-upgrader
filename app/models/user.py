from typing import Self
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
    def get_by_name(cls, session: Session, name: str, raise_exception=True):
        user = session.query(cls).where(User.name == name).one_or_none()
        if not user and raise_exception:
            raise MissingRecord("User `{name}` not found")
        return user

    @classmethod
    def create(cls, session: Session, name: str) -> str:
        if name == "admin":
            raise ValueError("name cannot be `admin`")

        password = secrets.token_urlsafe(128)
        user = User(
            name=name,
            password=argon2.using(rounds=4, memory_cost=65536).hash(password)
        )
        session.add(user)
        return password

    def create_new_password(self, session: Session) -> str:
        password = secrets.token_urlsafe(128)
        self.password = argon2.using(rounds=4, memory_cost=65536).hash(password)
        session.add(self)
        return password

    @classmethod
    def verify(cls, session: Session, name: str, password: str) -> Self | None:
        """ Validates the password and if it's correct return the User object. """
        user = cls.get_by_name(session, name, raise_exception=False)
        if not user:
            return None
        if argon2.verify(password, user.password):
            return user
        return None
