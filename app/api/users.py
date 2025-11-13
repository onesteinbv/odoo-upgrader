
from fastapi import APIRouter, Depends

from ..models.db import Session
from ..models.user import User

from ..security import admin_auth


router = APIRouter(dependencies=[Depends(admin_auth)])


@router.get("/all")
async def get_all():
    with Session() as session:
        users = session.query(User).all()
        return [{"name": user.name, "id": user.id} for user in users]


@router.post("/")
async def create(
    name: str,
):
    if name == "admin":
        raise ValueError("name cannot be `admin`")

    with Session.begin() as session:
        return User.create(session, name)


@router.post("/{name}/new-password")
async def create_new_password(
    name: str,
):
    with Session.begin() as session:
        user = User.get_by_name(session, name)
        new_password = user.create_new_password(session)
        session.commit()
    return new_password


@router.delete("/{name}")
async def delete(
    name: str, 
):
    with Session.begin() as session:
        User.delete_by_name(session, name)
