
from fastapi import HTTPException
from fastapi.params import Security
from fastapi.security.api_key import APIKeyHeader, APIKeyQuery
from starlette.status import HTTP_403_FORBIDDEN

from .settings import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
api_key_query = APIKeyQuery(name="api_key", auto_error=False)

def get_api_key(
    api_key_from_header: str = Security(api_key_header), 
    api_key_from_query: str = Security(api_key_query)
):
    """ Get api key from header or query parameter and validate it. """
    api_key = api_key_from_header or api_key_from_query
    if settings.api_key and api_key != settings.api_key:
        raise HTTPException(status_code=HTTP_403_FORBIDDEN, detail="Could not validate credentials")
    return api_key
