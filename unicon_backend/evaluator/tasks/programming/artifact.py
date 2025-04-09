from pathlib import Path
from typing import Annotated, cast

from pydantic import BaseModel, Field, model_validator

from unicon_backend.constants import MINIO_BUCKET
from unicon_backend.lib.file import BYTES_IN_KB, get_file_size

PrimitiveData = str | int | float | bool


class File(BaseModel):
    id: str  # Used to sync files between task files and testcases files
    path: str
    content: str

    on_minio: bool = False
    key: str | None = None

    # File size in KB. if 0, no limit
    size_limit: Annotated[int, Field(default=0, min=0)]

    trusted: bool = False

    @model_validator(mode="after")
    def check_path_is_safe(v):
        # NOTE: We only allow relative paths
        path = Path(v.path)
        if path.is_absolute():
            raise ValueError(f"Path {path} is not relative")
        # Path should not go outside the working directory
        if ".." in path.parts:
            raise ValueError(f"Path is suspicious (`..` found): {path}")

        return v

    @model_validator(mode="after")
    def check_minio_file(v):
        """If a file is on minio, content should be empty and key should be present."""
        if v.on_minio:
            if v.content:
                raise ValueError("Content should be empty for minio files")
            if not v.key:
                raise ValueError("Key should be present for minio files")
        return v

    @property
    def size_in_kb(self) -> float:
        if self.on_minio:
            return get_file_size(MINIO_BUCKET, cast("str", self.key)) / BYTES_IN_KB
        else:
            return len(self.content.encode("utf-8")) / BYTES_IN_KB
