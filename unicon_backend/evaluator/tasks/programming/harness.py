import importlib.resources
import importlib.resources.abc
from typing import Final

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
    return cst.Module(
        [
            *MPI_SANDBOX_MODULE.body,
            cst.If(
                test=cst.parse_expression("__name__ == '__main__'"),
                body=cst.IndentedBlock([*program.body]),
            ),
        ]
    )


def gbl_except_hook(program: cst.Module) -> cst.Module:
    return cst.Module([*GBL_EXCEPT_HANDLER.body, cst.Newline(), *program.body])  # type: ignore
