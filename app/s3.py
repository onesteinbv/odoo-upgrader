from contextlib import asynccontextmanager
from io import BytesIO
import aioboto3
import os
import logging
from .settings import settings

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def _client():
    session = aioboto3.Session()
    async with session.client(
        "s3", 
        endpoint_url="https://%s" % settings.s3.endpoint,
        aws_secret_access_key=settings.s3.secret_key,
        aws_access_key_id=settings.s3.access_key
    ) as s3:
        yield s3

async def upload(key: str, file: bytes):
    async with _client() as s3:
        try:
            file_io = BytesIO(file)
            await s3.upload_fileobj(file_io, settings.s3.bucket, key)
        except Exception as e:
            logger.error("Unable to upload to s3", exc_info=True)
            raise e


async def delete(key: str):
    async with _client() as s3:
        try:
            await s3.delete_object(Bucket=settings.s3.bucket, Key=key)
        except Exception as e:
            logger.error("Unable to delete object in s3", exc_info=True)
            raise e
