import importlib.resources

import libcst as cst

MPI_SANDBOX_MODULE: cst.Module = cst.parse_module(
    importlib.resources.files("unicon_backend")
    .joinpath("evaluator", "tasks", "programming", "templates", "mpi_sandbox.py")
    .read_text()
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
