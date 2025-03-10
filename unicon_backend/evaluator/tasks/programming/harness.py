import importlib.resources
import importlib.resources.abc
from typing import Final, cast

import libcst as cst

TEMPLATE_DIR: Final[importlib.resources.abc.Traversable] = importlib.resources.files(
    "unicon_backend"
).joinpath("evaluator", "tasks", "programming", "templates")

MPI_SANDBOX_MODULE: Final[cst.Module] = cst.parse_module(
    TEMPLATE_DIR.joinpath("mpi_sandbox.py").read_bytes()
)
GBL_EXCEPT_HANDLER: Final[cst.Module] = cst.parse_module(
    TEMPLATE_DIR.joinpath("global_except_hook.py").read_bytes()
)


def mpi_sandbox(program: cst.Module) -> cst.Module:
    """
    Adds the program body to the MPI sandbox module's main block.

    Assumes that the last element in MPI_SANDBOX_MODULE.body is the
    `if __name__ == "__main__":` block.
    """
    sandbox_preamble = MPI_SANDBOX_MODULE.body[:-1]
    main_block = cast(cst.If, MPI_SANDBOX_MODULE.body[-1])
    updated_main_block = main_block.with_changes(
        body=main_block.body.with_changes(
            body=[*main_block.body.body, cst.Newline(), *program.body]
        )
    )
    return MPI_SANDBOX_MODULE.with_changes(body=[*sandbox_preamble, updated_main_block])


def gbl_except_hook(program: cst.Module) -> cst.Module:
    return cst.Module([*GBL_EXCEPT_HANDLER.body, cst.Newline(), *program.body])  # type: ignore
