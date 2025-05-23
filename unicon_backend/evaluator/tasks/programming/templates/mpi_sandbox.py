import importlib
import importlib.util as importlib_util
import io
import multiprocessing
from contextlib import redirect_stderr, redirect_stdout
from multiprocessing import Process as MPProcess
from multiprocessing import Queue as MPQueue
from typing import Final

TASK_Q_STOP_SIGNAL: Final[str] = "STOP"


class IORedirect:
    def __init__(self):
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()

    def __enter__(self):
        self.stdout_redirector = redirect_stdout(self.stdout)
        self.stderr_redirector = redirect_stderr(self.stderr)
        self.stdout_redirector.__enter__()
        self.stderr_redirector.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.stdout_redirector.__exit__(exc_type, exc_value, traceback)
        self.stderr_redirector.__exit__(exc_type, exc_value, traceback)
        return False


def __exec_func(module_name: str, func_name: str, *args, **kwargs):
    module = importlib.import_module(module_name)
    parts = func_name.split(".")
    attr = module
    for part in parts:
        attr = getattr(attr, part)
    return attr(*args, **kwargs)  # type: ignore


def __exec_module(file_name: str, **globals):
    spec = importlib_util.find_spec(file_name)
    if spec and spec.loader:
        module = importlib_util.module_from_spec(spec)
        module.__dict__.update(globals)
        spec.loader.exec_module(module)


def worker(task_q: MPQueue, result_q: MPQueue):
    while True:
        if (msg := task_q.get()) == TASK_Q_STOP_SIGNAL:
            break

        file_name, function_name, args, kwargs = msg
        assert isinstance(file_name, str)

        error = result = None
        with IORedirect() as ior:
            try:
                if function_name:
                    module_name = file_name.replace(".py", "")
                    result = __exec_func(module_name, function_name, *args, **kwargs)
                else:
                    __exec_module(file_name, **kwargs)
            except Exception as e:
                error = e

        result_q.put((result, ior.stdout.getvalue(), ior.stderr.getvalue(), error))


if __name__ == "__main__":
    import atexit
    import json
    import sys

    multiprocessing.freeze_support()
    multiprocessing.set_start_method("spawn")

    task_q: MPQueue = MPQueue()
    result_q: MPQueue = MPQueue()

    worker_proc: MPProcess = MPProcess(target=worker, args=(task_q, result_q))
    worker_proc.start()

    def __mp_cleanup():
        task_q.put(TASK_Q_STOP_SIGNAL)
        worker_proc.join()
        task_q.close()
        task_q.join_thread()
        result_q.close()
        result_q.join_thread()

    atexit.register(__mp_cleanup)

    def __print_stderr_and_exit(module_name: str, func_name: str | None, err: Exception):
        print(  # noqa: T201
            json.dumps({"file_name": module_name, "function_name": func_name, "error": str(err)}),
            file=sys.stderr,
        )
        sys.exit(1)

    def __call_function_unsafe(
        file_name: str, function_name: str | None, allow_error: bool, *args, **kwargs
    ):
        result = err = None
        with IORedirect() as ior:
            try:
                if function_name:
                    result = __exec_func(file_name, function_name, *args, **kwargs)
                else:
                    __exec_module(file_name, **kwargs)
            except Exception as e:
                err = e

        if not allow_error and err is not None:
            __print_stderr_and_exit(file_name, function_name, err)

        return result, ior.stdout.getvalue(), ior.stderr.getvalue(), err

    def __call_function_safe(
        file_name: str, function_name: str, allow_error: bool, *args, **kwargs
    ):
        task_q.put((file_name, function_name, args, kwargs))
        result, stdout, stderr, err = result_q.get()

        if not allow_error and err is not None:
            __print_stderr_and_exit(file_name, function_name, err)

        return result, stdout, stderr, err
