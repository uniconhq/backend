import sys


def _gbl_except_hook(exc_type: type[BaseException], exc: BaseException, _exc_tb) -> None:
    # Print the original exception information to preserve stderr output
    sys.__excepthook__(exc_type, exc, _exc_tb)
    if exc_type in (MemoryError, ImportError):
        # NOTE: We assume that dependencies and libraries are installed properly, hence if
        #       there is an ImportError, we raise it as a memory-related error
        sys.exit(139)  # Segmentation fault


sys.excepthook = _gbl_except_hook
