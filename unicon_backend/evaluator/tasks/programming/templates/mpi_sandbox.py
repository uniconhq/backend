import atexit
import importlib
import importlib.util as importlib_util
import io
import json
import multiprocessing
import sys
from contextlib import redirect_stderr, redirect_stdout


def call_function_from_file(file_name: str, function_name: str, *args, **kwargs):
    with redirect_stdout(io.StringIO()) as stdout, redirect_stderr(io.StringIO()) as stderr:
        module_name = file_name.replace(".py", "")
        module = importlib.import_module(module_name)
        func = getattr(module, function_name)
        error = None
        try:
            func(*args, **kwargs)
        except Exception as e:
            error = e
        return func(*args, **kwargs), stdout.getvalue(), stderr.getvalue(), error


def run_code_from_file(file_name: str, **variables):
    spec = importlib_util.find_spec(file_name)
    module = importlib_util.module_from_spec(spec)
    module.__dict__.update(variables)
    with redirect_stdout(io.StringIO()) as stdout, redirect_stderr(io.StringIO()) as stderr:
        error = None
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            error = e
    return None, stdout.getvalue(), stderr.getvalue(), error


def worker(task_queue: multiprocessing.Queue, result_queue: multiprocessing.Queue):
    while True:
        task = task_queue.get()
        if task == "STOP":
            break

        file_name, function_name, args, kwargs = task

        if function_name:
            result, stdout, stderr, error = call_function_from_file(
                file_name, function_name, *args, **kwargs
            )
        else:
            result, stdout, stderr, error = run_code_from_file(file_name, **kwargs)
        result_queue.put((result, stdout, stderr, error))


multiprocessing.freeze_support()
multiprocessing.set_start_method("spawn")
task_queue = multiprocessing.Queue()
result_queue = multiprocessing.Queue()

process = multiprocessing.Process(target=worker, args=(task_queue, result_queue))
process.start()


def call_function_safe(file_name: str, function_name: str, allow_error: bool, *args, **kwargs):
    task_queue.put((file_name, function_name, args, kwargs))
    result, stdout, stderr, err = result_queue.get()
    if not allow_error and err is not None:
        print(  # noqa: T201
            json.dumps({"file_name": file_name, "function_name": function_name, "error": str(err)})
        )
        sys.exit(1)
    return result, stdout, stderr, err


def run_code_unsafe(file_name: str, allow_error: bool, **variables):
    spec = importlib_util.find_spec(file_name)
    module = importlib_util.module_from_spec(spec)
    module.__dict__.update(variables)
    spec.loader.exec_module(module)


def call_function_unsafe(file_name: str, function_name: str, allow_error: bool, *args, **kwargs):
    with redirect_stdout(io.StringIO()) as stdout, redirect_stderr(io.StringIO()) as stderr:
        try:
            if function_name:
                module = importlib.import_module(file_name)
                func = getattr(module, function_name)
                result = func(*args, **kwargs)
            else:
                run_code_unsafe(file_name, allow_error, **kwargs)
            err = None
        except Exception as e:
            result = None
            err = e
    if not allow_error and err is not None:
        print(  # noqa: T201
            json.dumps({"file_name": file_name, "function_name": function_name, "error": str(err)})
        )
        sys.exit(1)
    return result, stdout.getvalue(), stderr.getvalue(), err


def cleanup():
    task_queue.put("STOP")
    process.join()


atexit.register(cleanup)
