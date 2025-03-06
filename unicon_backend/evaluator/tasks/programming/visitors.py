import libcst as cst
from pydantic import BaseModel

from unicon_backend.lib.cst import cst_var


class Arg(BaseModel):
    name: str
    type: str | None
    default: str | None


class ParsedFunction(BaseModel):
    name: str
    args: list[Arg]
    kwargs: list[Arg]
    star_args: bool
    star_kwargs: bool
    return_type: str | None


def get_default(param: cst.Param) -> str | None:
    return cst.Module([]).code_for_node(param.default) if param.default is not None else None


def get_type_annotation(annotation: cst.Annotation | None) -> str:
    if not annotation:
        return "Any"

    return (
        cst.Module([])
        .code_for_node(cst.Param(name=cst_var("placeholder"), annotation=annotation, star=""))
        .split(":", 1)[1]
        .strip()
    )


class TypingCollector(cst.CSTVisitor):
    def __init__(self):
        self.stack: list[str] = []
        self.results: list[ParsedFunction] = []

    def visit_ClassDef(self, node: cst.ClassDef):
        self.stack.append(node.name.value)
        return False

    def leave_ClassDef(self, _: cst.ClassDef) -> None:
        self.stack.pop()

    def visit_FunctionDef(self, node: cst.FunctionDef) -> bool | None:
        function_name = node.name.value
        is_method = len(self.stack) > 0
        self.stack.append(function_name)

        name = ".".join(
            [n for n in self.stack][:-1]
            # If it's a Class's __init__ method, use the Class directly as the function name
            + ([function_name] if not is_method or function_name != "__init__" else [])
        )

        # Remove any past declaration of the function, since this would overwrite it
        self.results = [result for result in self.results if result.name != name]

        self.results.append(
            ParsedFunction(
                name=name,
                args=[
                    Arg.model_validate(
                        {
                            "name": param.name.value,
                            "default": get_default(param),
                            "type": get_type_annotation(param.annotation),
                        }
                    )
                    for param in node.params.params
                ],
                kwargs=[
                    Arg.model_validate(
                        {
                            "name": param.name.value,
                            "default": get_default(param),
                            "type": get_type_annotation(param.annotation),
                        }
                    )
                    for param in node.params.kwonly_params
                ],
                star_args=isinstance(node.params.star_arg, cst.Param),
                star_kwargs=node.params.star_kwarg is not None,
                return_type=get_type_annotation(node.returns),
            )
        )
        # Stop traversal (don't support inner functions)
        return False

    def leave_FunctionDef(self, _: cst.FunctionDef) -> None:
        self.stack.pop()
