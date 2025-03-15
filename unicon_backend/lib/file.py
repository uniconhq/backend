import io
import logging
import mimetypes
import pathlib
import uuid

from fastapi import UploadFile
from minio import Minio, S3Error

from unicon_backend.constants import MINIO_ACCESS_KEY, MINIO_BUCKET, MINIO_HOST, MINIO_SECRET_KEY

logger = logging.getLogger(__name__)

_client = Minio(MINIO_HOST, access_key=MINIO_ACCESS_KEY, secret_key=MINIO_SECRET_KEY, secure=False)

BYTES_IN_KB = 1024


async def upload_fastapi_file(file: UploadFile) -> str:
    """
    Upload a file from FastAPI's UploadFile object to Minio.
    Returns file's minio_key.
    """
    content_type = mimetypes.guess_type(file.filename or "")[0] or "application/octet-stream"
    ext = pathlib.Path(file.filename).suffix if file.filename else ""
    key = get_valid_key(ext)
    upload_file(MINIO_BUCKET, key, await file.read(), content_type)
    return key


def delete_file(bucket_name: str, object_name: str):
    _client.remove_object(bucket_name, object_name)


def guess_content_type(filename: str | None) -> str:
    default = "application/octet-stream"
    if not filename:
        return default
    return mimetypes.guess_type(filename)[0] or default


def get_valid_key(ext: str) -> str:
    key = str(uuid.uuid4()) + ext
    while file_exists(MINIO_BUCKET, key):
        key = str(uuid.uuid4()) + ext
    return key


def file_exists(bucket_name: str, object_name: str) -> bool:
    try:
        _client.stat_object(bucket_name, object_name)
    except S3Error:
        return False
    return True


def upload_file(bucket_name: str, object_name: str, data: bytes, content_type: str | None = None):
    """Upload a file to Minio.

    Note: you can upload files without content_type - but since we are using UUIDs for object names,
    Minio will not be able to infer the content type from the object name (and cannot show you a preview on the GUI without this.)
    """

    # Make the bucket if it doesn't exist.
    found = _client.bucket_exists(bucket_name)
    if not found:
        _client.make_bucket(bucket_name)
        logger.info(f"Bucket {bucket_name} created")

    _client.put_object(
        bucket_name,
        object_name,
        io.BytesIO(data),
        len(data),
        content_type=content_type or "application/octet-stream",
    )


def download_file(bucket_name: str, object_name: str) -> bytes:
    response = _client.get_object(bucket_name, object_name)
    data = response.read()
    response.close()
    response.release_conn()
    return data


def get_file_size(bucket_name: str, object_name: str) -> int:
    size = _client.stat_object(bucket_name, object_name).size
    if size is None:
        raise ValueError("Size of the file is None")
    return size
