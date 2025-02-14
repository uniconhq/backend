from enum import Enum
from typing import NewType, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, model_validator

from unicon_backend.evaluator.tasks.programming.artifact import File

JobId = NewType("JobId", UUID)


class Language(str, Enum):
    PYTHON = "PYTHON"


class PythonVersion(str, Enum):
    """Ensure consistency with `uv python list`"""

    PYTHON_3_7_9 = "3.7.9"
    PYTHON_3_8_20 = "3.8.20"
    PYTHON_3_9_21 = "3.9.21"
    PYTHON_3_10_12 = "3.10.12"
    PYTHON_3_11_9 = "3.11.9"
    PYTHON_3_11_11 = "3.11.11"
    PYTHON_3_12_8 = "3.12.8"
    PYTHON_3_13_1 = "3.13.1"

    @classmethod
    def list(cls) -> list[str]:
        return [member.value for member in cls]


class ExtraOptions(BaseModel):
    version: PythonVersion | None = None
    requirements: str | None = None


class ComputeContext(BaseModel):
    language: Language
    time_limit_secs: float
    memory_limit_mb: int

    slurm: bool = False
    # Additional options for `srun`
    # e.g. [--gpus", "1", "--cpus-per-task", "2"]
    slurm_options: list[str] = []
    # Use python interpreter present in the allocated slurm node
    # If true, ignores python version specified under `extra_options` and default fallback python version
    slurm_use_system_py: bool = False

    extra_options: ExtraOptions | None = None

    @model_validator(mode="after")
    def non_negative_and_non_zero_limits(self) -> Self:
        if self.time_limit_secs <= 0:
            raise ValueError("Time limit must be non-negative and non-zero")
        if self.memory_limit_mb <= 0:
            raise ValueError("Memory limit must be non-negative and non-zero")
        return self


class Status(str, Enum):
    OK = "OK"
    MLE = "MLE"
    TLE = "TLE"
    RTE = "RTE"
    WA = "WA"


class ProgramResult(BaseModel):
    status: Status
    stdout: str
    stderr: str

    elapsed_time_ns: int | None = None

    # Tracking fields
    id: int  # Corresponds to the testcase id of the problem


class JobResult(BaseModel):
    model_config = ConfigDict(use_enum_values=True)
    success: bool
    error: str | None
    results: list[ProgramResult]

    # Tracking fields
    id: JobId


class RunnerProgram(BaseModel):
    entrypoint: str
    files: list[File]

    # Tracking fields
    id: int  # Corresponds to the testcase id of the problem

    @model_validator(mode="after")
    def check_entrypoint_exists_in_files(self) -> Self:
        if not any(file.name == self.entrypoint for file in self.files):
            raise ValueError(f"Entrypoint {self.entrypoint} not found in program files")
        return self


class RunnerJob(BaseModel):
    programs: list[RunnerProgram]
    context: ComputeContext

    # Tracking fields
    id: JobId

    @classmethod
    def create(cls, programs: list[RunnerProgram], environment: ComputeContext) -> "RunnerJob":
        return RunnerJob(id=JobId(uuid4()), programs=programs, context=environment)
