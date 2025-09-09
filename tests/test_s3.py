import pytest
from app import s3

@pytest.mark.asyncio
async def test_upload_and_delete():
    await s3.upload("123", b"test")
    await s3.delete("123")