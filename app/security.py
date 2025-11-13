
import uuid
from fastapi import HTTPException
from fastapi.params import Security
from fastapi.security.http import HTTPBasic, HTTPBasicCredentials
from starlette.status import HTTP_401_UNAUTHORIZED

from .models.db import Session
from .models.user import User

from .settings import settings

http_basic_auth = HTTPBasic(auto_error=False)

def admin_auth(
    http_credentials: HTTPBasicCredentials = Security(http_basic_auth), 
):
    if not http_credentials:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED, 
            detail="No credentials provided", 
            headers={"WWW-Authenticate": "Basic"}
        )
    """ Admin only authentication. """
    if http_credentials.username != "admin":
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED, 
            detail="Could not validate credentials", 
            headers={"WWW-Authenticate": "Basic"})

    if http_credentials.password != settings.admin_password:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials", 
            headers={"WWW-Authenticate": "Basic"}
        )


def user_auth(
    http_credentials: HTTPBasicCredentials = Security(http_basic_auth)
) -> uuid.UUID | None:
    """ Allow admin and user login """
    if not http_credentials:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED, 
            detail="No credentials provided", 
            headers={"WWW-Authenticate": "Basic"}
        )
    if http_credentials.username == "admin":
        if http_credentials.password != settings.admin_password:
            raise HTTPException(
                status_code=HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials", 
                headers={"WWW-Authenticate": "Basic"}
            )
        return None
        
    with Session() as session:
        user = User.verify(
            session,
            http_credentials.username, 
            http_credentials.password
        )
        if not user:
            raise HTTPException(
                status_code=HTTP_401_UNAUTHORIZED, 
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Basic"}
            )
    return user.id
