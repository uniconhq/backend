from pathlib import Path

from pydantic import BaseModel, model_validator

PrimitiveData = str | int | float | bool


class File(BaseModel):
    path: str
    content: str

    trusted: bool = False

    on_minio: bool = False
    key: str | None = None

    @model_validator(mode="after")
    def check_path_is_safe(v):
        # NOTE: We only allow relative paths
        path = Path(v.path)
        if path.is_absolute():
            raise ValueError(f"Path {path} is not relative")
        # Path should not go outside the working directory
        if ".." in path.parts:
            raise ValueError(f"Path is suspicious (`..` found): {path}")

        # In case path has a ./ in front of it
        v.path = str(path)
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
