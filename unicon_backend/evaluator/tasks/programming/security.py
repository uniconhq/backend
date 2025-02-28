import libcst as cst

WORKER_TEMPLATE = cst.parse_module("""
import os
import io
from contextlib import redirect_stdout, redirect_stderr                                   

def call_function_from_file(file_name, function_name, *args, **kwargs):
    with redirect_stdout(io.StringIO()) as stdout, redirect_stderr(io.StringIO()) as stderr:  
        module_name = file_name.replace(".py", "")
        module = importlib.import_module(module_name)
        func = getattr(module, function_name)
        return func(*args, **kwargs), stdout.getvalue(), stderr.getvalue()
                                   
def run_code_from_file(file_name, **variables):
    spec = importlib.util.find_spec(file_name)
    module = importlib.util.module_from_spec(spec)
    module.__dict__.update(variables)
    with redirect_stdout(io.StringIO()) as stdout, redirect_stderr(io.StringIO()) as stderr: 
        spec.loader.exec_module(module)
    return None, stdout.getvalue(), stderr.getvalue()


def worker(task_queue, result_queue):
    while True:
        task = task_queue.get()
        if task == "STOP":
            break

        file_name, function_name, args, kwargs = task
        try:
            if function_name:
                result, stdout, stderr = call_function_from_file(file_name, function_name, *args, **kwargs)
            else:
                result, stdout, stderr = run_code_from_file(file_name, **kwargs)           
            result_queue.put((result, stdout, stderr, None))
        except Exception as e:
            result_queue.put((None, None, None, e))
""")

MPI_CLEANUP_TEMPLATE = cst.parse_module("""
import atexit

def cleanup():
    task_queue.put("STOP")
    process.join()

atexit.register(cleanup)
""")

ENTRYPOINT_TEMPLATE = cst.parse_module("""
multiprocessing.freeze_support()
multiprocessing.set_start_method("spawn")
task_queue = multiprocessing.Queue()
result_queue = multiprocessing.Queue()

process = multiprocessing.Process(target=worker, args=(task_queue, result_queue))
process.start()

def call_function_safe(file_name, function_name, allow_error, *args, **kwargs):
    task_queue.put((file_name, function_name, args, kwargs))
    result, stdout, stderr, err = result_queue.get()
    if not allow_error and err is not None:
        print(json.dumps({"file_name": file_name, "function_name": function_name, "error": str(err)}))
        sys.exit(1)
    return result, stdout, stderr, err

def run_code_unsafe(file_name, allow_error, **variables):
    spec = importlib.util.find_spec(file_name)
    module = importlib.util.module_from_spec(spec)
    module.__dict__.update(variables)
    spec.loader.exec_module(module)

def call_function_unsafe(file_name, function, allow_error, *args, **kwargs):
    with redirect_stdout(io.StringIO()) as stdout, redirect_stderr(io.StringIO()) as stderr: 
        try:
            result = function(*args, **kwargs) if function else run_code_unsafe(file_name, allow_error, **kwargs)
            err = None
        except Exception as e:
            result = None
            err = e
    if not allow_error and err is not None:
        print(json.dumps({"file_name": file_name, "function_name": function_name, "error": str(err)}))
        sys.exit(1)
    return result, stdout.getvalue(), stderr.getvalue(), err
""")


def mpi_sandbox(program: cst.Module) -> cst.Module:
    return cst.Module(
        [
            cst.parse_statement("import importlib, multiprocessing, sys, json"),
            *WORKER_TEMPLATE.body,
            cst.If(
                test=cst.parse_expression("__name__ == '__main__'"),
                body=cst.IndentedBlock(
                    [*ENTRYPOINT_TEMPLATE.body, *MPI_CLEANUP_TEMPLATE.body, *program.body]
                ),
            ),
        ]
    )
