import abc
import logging
import re
from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from enum import Enum, StrEnum
from functools import cached_property
from itertools import count
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, Final, Literal, Self, cast

import libcst as cst
from pydantic import BaseModel, Field, PrivateAttr, model_validator

from unicon_backend.evaluator.tasks.programming.artifact import File, PrimitiveData
from unicon_backend.evaluator.tasks.programming.types import UniconType
from unicon_backend.lib.common import CustomSQLModel
from unicon_backend.lib.cst import (
    UNUSED_VAR,
    Program,
    ProgramBody,
    ProgramFragment,
    ProgramVariable,
    assemble_fragment,
    cst_expr,
    cst_str,
    cst_var,
    hoist_imports,
)
from unicon_backend.lib.graph import Graph, GraphEdge, GraphNode, NodeSocket
from unicon_backend.lib.helpers import partition

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)

type SocketId = str


class StepType(str, Enum):
    PY_RUN_FUNCTION = "PY_RUN_FUNCTION_STEP"
    OBJECT_ACCESS = "OBJECT_ACCESS_STEP"

    # I/O Operations
    INPUT = "INPUT_STEP"
    OUTPUT = "OUTPUT_STEP"

    # Control Flow Operations
    LOOP = "LOOP_STEP"
    IF_ELSE = "IF_ELSE_STEP"

    # Comparison Operations
    STRING_MATCH = "STRING_MATCH_STEP"


STEP_TYPE_SHORTHANDS: Mapping[StepType, str] = {
    StepType.PY_RUN_FUNCTION: "py_run_func",
    StepType.OBJECT_ACCESS: "obj_access",
    StepType.INPUT: "in",
    StepType.OUTPUT: "out",
    StepType.LOOP: "loop",
    StepType.IF_ELSE: "if_else",
    StepType.STRING_MATCH: "str_match",
}


class SocketType(str, Enum):
    DATA = "DATA"
    CONTROL = "CONTROL"


class SocketDir(str, Enum):
    IN = "IN"
    OUT = "OUT"


class StepSocket(NodeSocket[str]):
    type: SocketType = SocketType.DATA
    # User facing name of the socket
    label: str = ""
    # The data that the socket holds
    data: PrimitiveData | File | None = None

    data_type: UniconType | None = None

    # for PythonObject
    # {"name": "PythonTypeName"}
    data_type_metadata: dict[str, Any] | None = None

    _dir: SocketDir = PrivateAttr()

    @property
    def alias(self) -> str:
        return ".".join([self.type.value, self._dir.value, self.label])


Range = tuple[int, int]


class Step[SocketT: StepSocket](GraphNode[str, SocketT], abc.ABC):
    type: StepType

    _debug: bool = False

    # Socket aliases that are used to refer to subgraph sockets
    subgraph_socket_aliases: ClassVar[set[str]] = set()
    # The required number of data sockets
    required_control_io: ClassVar[tuple[Range, Range]] = ((-1, 1), (-1, 1))
    # The required number of control sockets
    # The maximum number by default is 1 for both input and output control sockets (CONTROL.IN and CONTROL.OUT)
    required_data_io: ClassVar[tuple[Range, Range]] = ((-1, -1), (-1, -1))

    def model_post_init(self, __context):
        # fmt: off
        for socket in self.inputs: socket._dir = SocketDir.IN
        for socket in self.outputs: socket._dir = SocketDir.OUT
        # fmt: on

    @model_validator(mode="after")
    def check_required_inputs_and_outputs(self) -> Self:
        def satisfies_required(expected: Range, got: int) -> bool:
            match expected:
                case (-1, -1):
                    return True
                case (-1, upper_bound):
                    return got <= upper_bound
                case (lower_bound, -1):
                    return got >= lower_bound
                case (lower_bound, upper_bound):
                    return lower_bound <= got <= upper_bound
                case _:
                    return False  # This should never happen

        is_data_socket: Callable[[StepSocket], bool] = lambda socket: socket.type == SocketType.DATA

        num_data_in, num_control_in = list(map(len, partition(is_data_socket, self.inputs)))
        num_data_out, num_control_out = list(map(len, partition(is_data_socket, self.outputs)))

        for got, expected, label in zip(
            (num_data_in, num_data_out, num_control_in, num_control_out),
            self.required_data_io + self.required_control_io,
            ("data input", "data output", "control input", "control output"),
            strict=True,
        ):
            if not satisfies_required(expected, got):
                min_expected, max_expected = expected
                expected_range = (
                    f"exactly {min_expected}"
                    if min_expected == max_expected
                    else f"between {min_expected} and {max_expected}"
                )
                raise ValueError(
                    f"{self.type.value} requires {expected_range} {label} sockets, found {got}"
                )

        return self

    @cached_property
    def data_in(self) -> Sequence[SocketT]:
        return [socket for socket in self.inputs if socket.type == SocketType.DATA]

    @cached_property
    def data_out(self) -> Sequence[SocketT]:
        return [socket for socket in self.outputs if socket.type == SocketType.DATA]

    @cached_property
    def alias_map(self) -> dict[str, SocketT]:
        return {socket.alias: socket for socket in self.inputs + self.outputs}

    def run_subgraph(self, subgraph_socket_alias: str, graph: "ComputeGraph") -> Program:
        assert subgraph_socket_alias in self.subgraph_socket_aliases
        subgraph_socket = self.alias_map.get(subgraph_socket_alias)
        assert subgraph_socket is not None
        return graph.run(
            debug=self._debug, node_ids=self._get_subgraph_node_ids(subgraph_socket.id, graph)
        )

    def get_all_subgraph_node_ids(self, graph: "ComputeGraph") -> set[str]:
        """Returns ids of nodes that part of a subgraph"""
        subgraph_node_ids: set[str] = set()
        for socket_alias in self.subgraph_socket_aliases:
            if socket := self.alias_map.get(socket_alias):
                subgraph_node_ids |= self._get_subgraph_node_ids(socket.id, graph)

        return subgraph_node_ids

    def _get_subgraph_node_ids(self, subgraph_socket_id: str, graph: "ComputeGraph") -> set[str]:
        subgraph_socket = self.get_socket(subgraph_socket_id)
        assert subgraph_socket is not None

        connected_node_ids = graph.get_connected_nodes(self.id, subgraph_socket_id)
        # NOTE: Assumes that there is only one edge connected to the subgraph socket
        if (start_node_id := connected_node_ids[0] if connected_node_ids else None) is None:
            # If no subgraph start node is found, then the subgraph is empty
            # This can happen if the a step allows an empty subgraph - we defer the check to the step
            return set()

        subgraph_node_ids: set[str] = set()
        bfs_queue: deque[str] = deque([start_node_id])
        while len(bfs_queue):
            frontier_node_id = bfs_queue.popleft()
            # NOTE: Ignore current node to avoid unintended backtracking
            if frontier_node_id == self.id or frontier_node_id in subgraph_node_ids:
                continue

            subgraph_node_ids.add(frontier_node_id)
            for out_edge in graph.out_edges_index[frontier_node_id]:
                if graph.link_type(out_edge) == SocketType.CONTROL:
                    bfs_queue.append(graph.node_index[out_edge.to_node_id].id)

            for in_edge in graph.in_edges_index[frontier_node_id]:
                if graph.link_type(in_edge) == SocketType.CONTROL:
                    bfs_queue.append(graph.node_index[in_edge.from_node_id].id)

        return subgraph_node_ids

    @abc.abstractmethod
    def run(
        self,
        graph: "ComputeGraph",
        in_vars: dict[SocketId, ProgramVariable],
        in_files: dict[SocketId, File],
    ) -> ProgramFragment: ...


class InputSocket(StepSocket):
    public: bool = Field(default=True)


class InputStep(Step[InputSocket]):
    type: Literal[StepType.INPUT]

    required_data_io: ClassVar[tuple[Range, Range]] = ((0, 0), (1, -1))

    inputs: list[InputSocket] = []
    is_user: bool = False  # Whether the input is provided by the user

    @model_validator(mode="after")
    def check_non_empty_data_outputs(self) -> Self:
        if (
            not self.is_user
            and (empty_socket_ids := [socket.id for socket in self.data_out if socket.data is None])
            is None
        ):
            raise ValueError(f"Missing data for output sockets {','.join(empty_socket_ids)}")
        return self

    def run(self, graph: "ComputeGraph", *_) -> ProgramFragment:
        def _parse(data: str | int | float | bool) -> cst.BaseExpression:
            return cst.parse_expression(
                repr(data)
                if not isinstance(data, str)
                else (f'"{data}"' if not data.startswith(graph.VAR_PREFIX) else data)
            )

        program = []
        # If the input is a `File`, we skip the serialization and just pass the file object
        # directly to the next step. This is handled by the `ComputeGraph` class
        for socket in filter(lambda s: isinstance(s.data, PrimitiveData), self.data_out):
            program.append(
                cst.Assign(
                    targets=[cst.AssignTarget(graph.get_link_var(self, socket))],
                    value=_parse(cast("PrimitiveData", socket.data)),
                )
            )

        for socket in filter(lambda s: isinstance(s.data, File), self.data_out):
            program.append(
                cst.Assign(
                    targets=[cst.AssignTarget(graph.get_link_var(self, socket))],
                    value=_parse(
                        # The prepended `src/` is the directory unicon-runner would create the file in.
                        # This is necessary because the working directory is the folder containing `src/`
                        "src/" + cast("File", socket.data).path,
                    ),
                )
            )

        return program

    def redact_private_fields(self) -> None:
        for socket in self.outputs:
            if not socket.public:
                socket.data = None


class Operator(StrEnum):
    LESS_THAN = "<"
    EQUAL = "="
    GREATER_THAN = ">"


class Comparison(CustomSQLModel):
    operator: Operator
    value: Any

    @model_validator(mode="after")
    def check_value_type(self) -> Self:
        """For < and >, check the operator can be compared (i.e. primitive)"""
        if self.operator == Operator.EQUAL:
            return self
        if not isinstance(self.value, PrimitiveData):
            raise ValueError(f"Invalid comparison value {self.value} for operator {self.operator}")
        return self

    def compare(self, actual_value: Any):
        try:
            match self.operator:
                case Operator.EQUAL:
                    return actual_value == self.value
                case Operator.LESS_THAN:
                    return actual_value < self.value
                case Operator.GREATER_THAN:
                    return actual_value > self.value
                case _:
                    return False
        except:
            # if there was an exception, the type returned was incorrect.
            # so return False.
            return False  # noqa: B012


class OutputSocket(StepSocket):
    comparison: Comparison | None = None
    """Comparison to be made with the output of the socket. Optional."""
    public: bool = True
    """Whether output of the socket should be shown to less priviledged users."""


class OutputStep(Step[OutputSocket]):
    type: Literal[StepType.OUTPUT]

    required_data_io: ClassVar[tuple[Range, Range]] = ((1, -1), (0, 0))

    outputs: list[OutputSocket] = []

    def run(
        self, _graph: "ComputeGraph", in_vars: dict[SocketId, ProgramVariable], *_
    ) -> ProgramFragment:
        result_dict = cst.Dict(
            [
                cst.DictElement(
                    key=cst_str(socket.id),
                    value=in_vars[socket.id] if socket.id in in_vars else cst_var("None"),
                )
                for socket in self.data_in
            ]
        )
        return [
            cst.Import([cst.ImportAlias(name=cst_var("json"))]),
            cst.Expr(
                cst.Call(
                    func=cst_var("print"),
                    args=[
                        cst.Arg(
                            cst.Call(
                                func=cst.Attribute(value=cst_var("json"), attr=cst_var("dumps")),
                                args=[
                                    cst.Arg(result_dict),
                                    cst.Arg(cst_var("str"), keyword=cst_var("default")),
                                ],
                            )
                        )
                    ],
                )
            ),
        ]

    def redact_private_fields(self):
        self.inputs = [socket for socket in self.inputs if socket.public]


class StringMatchStep(Step[StepSocket]):
    type: Literal[StepType.STRING_MATCH]

    required_data_io: ClassVar[tuple[Range, Range]] = ((2, 2), (1, 1))

    def run(
        self, graph: "ComputeGraph", in_vars: dict[SocketId, ProgramVariable], *_
    ) -> ProgramFragment:
        def get_match_op(s: StepSocket) -> cst.BaseExpression:
            assert not isinstance(s.data, File)  # TODO: More robust validation for data type
            if ret_expr := in_vars.get(
                s.id,
                cst_expr(cast("PrimitiveData", s.data))
                if isinstance(s.data, str | bool | int | float)
                else None,
            ):
                return ret_expr
            raise ValueError(f"Missing data for socket {self.id}:{s.id}")

        def str_cast(expr: cst.BaseExpression) -> cst.Call:
            return cst.Call(cst_var("str"), args=[cst.Arg(expr)])

        match_result_socket, [op_1, op_2] = self.data_out[0], self.data_in

        return [
            cst.Assign(
                targets=[cst.AssignTarget(graph.get_link_var(self, match_result_socket))],
                value=cst.Comparison(
                    left=str_cast(get_match_op(op_1)),
                    comparisons=[cst.ComparisonTarget(cst.Equal(), str_cast(get_match_op(op_2)))],
                ),
            )
        ]


class ObjectAccessStep(Step[StepSocket]):
    type: Literal[StepType.OBJECT_ACCESS]

    required_data_io: ClassVar[tuple[Range, Range]] = ((1, 1), (1, 1))

    key: str

    def run(
        self, graph: "ComputeGraph", in_vars: dict[SocketId, ProgramVariable], *_
    ) -> ProgramFragment:
        return [
            cst.Assign(
                targets=[cst.AssignTarget(graph.get_link_var(self, self.data_out[0]))],
                value=cst.Subscript(
                    value=in_vars[self.data_in[0].id],
                    slice=[cst.SubscriptElement(cst.Index(cst_str(self.key)))],
                ),
            )
        ]


class ArgMetadata(BaseModel):
    position: int
    arg_name: str | None = None


class PyRunFunctionSocket(StepSocket):
    """
    For every field in this class, only one of the fields is truthy at a time.

    Function Input:
    import_as_module: true --> the file we are importing from
    arg_metadata: true --> its an argument
    kwarg_name: true --> its a keyword argument. (no function will use this too to inject variables)

    Function Output:
    Everything below is falsy: --> the result of the function.
    handles_error: true --> error of the output. It is actually not safe to use this as an output because it is not serializable.
    handles_stdout: true --> stdout from running the function.
    handles_stderr: true --> stderr from running the function.
    """

    import_as_module: bool = False

    arg_metadata: ArgMetadata | None = None
    kwarg_name: str | None = None

    handles_error: bool = False
    handles_stdout: bool = False
    handles_stderr: bool = False


# NOTE: These function ids should align with harnesses defined in `templates/mpi_sandbox.py`
CALL_FUNCTION_SAFE_FUNC_ID: Final[str] = "__call_function_safe"
CALL_FUNCTION_UNSAFE_FUNC_ID: Final[str] = "__call_function_unsafe"


class PyRunFunctionStep(Step[PyRunFunctionSocket]):
    type: Literal[StepType.PY_RUN_FUNCTION]

    required_data_io: ClassVar[tuple[Range, Range]] = ((1, -1), (1, 4))

    # If function_identifier is None, we just run the module. Result doesn't make sense in this scenario.
    function_identifier: str | None = None
    allow_error: bool = False
    propagate_stdout: bool = False
    propagate_stderr: bool = False

    @model_validator(mode="after")
    def check_module_file_input(self) -> Self:
        if not any(socket.import_as_module for socket in self.data_in):
            raise ValueError("No module provided!")
        return self

    @model_validator(mode="after")
    def check_error_pipe_socket(self) -> Self:
        error_pipe_socket = any(socket.handles_error for socket in self.data_out)
        if self.allow_error and not error_pipe_socket:
            raise ValueError("Missing error pipe socket, but `allow_error` is True")
        if not self.allow_error and error_pipe_socket:
            raise ValueError("Unexpected error pipe socket, `allow_error` is False")
        return self

    @property
    def args(self) -> Sequence[PyRunFunctionSocket]:
        return sorted(
            [socket for socket in self.data_in if socket.arg_metadata],
            key=lambda s: cast("ArgMetadata", s.arg_metadata).position,
        )

    @property
    def kwargs(self) -> Sequence[PyRunFunctionSocket]:
        return [socket for socket in self.data_in if socket.kwarg_name]

    def run(
        self,
        graph: "ComputeGraph",
        in_vars: dict[SocketId, ProgramVariable],
        in_files: dict[SocketId, File],
    ) -> ProgramFragment:
        def has_data(s: StepSocket) -> bool:
            return in_vars.get(s.id, s.data) is not None

        def get_param_expr(s: StepSocket) -> cst.BaseExpression:
            # TODO: More robust validation for data type
            data = s.data
            # If the data is a file, we pass the file path directly to the function
            if isinstance(data, File):
                if result := in_vars.get(s.id):
                    return result
            elif ret_expr := in_vars.get(s.id, cst_expr(data) if data is not None else None):
                return ret_expr
            raise ValueError(f"Missing data for socket {self.id}:{s.id}")

        # Get the input file that we are running the function from
        module_s = next(socket for socket in self.data_in if socket.import_as_module)
        if (module_file := in_files.get(module_s.id)) is None:
            raise ValueError("Missing module file!")

        # NOTE: Assume that the program file is always a Python file
        module_name = module_file.path.split(".py")[0].replace("/", ".")

        args = [cst.Arg(get_param_expr(s)) for s in self.args if has_data(s)]
        kwargs = [cst.Arg(get_param_expr(s), keyword=cst_var(cast("str", s.kwarg_name))) for s in self.kwargs if has_data(s)]  # fmt: skip

        out_var = next(
            (
                graph.get_link_var(self, s)
                for s in self.data_out
                if not s.handles_error and not s.handles_stdout and not s.handles_stderr
            ),
            UNUSED_VAR,
        )
        if not out_var:
            raise ValueError("Missing result socket")
        error_var = next(
            (graph.get_link_var(self, s) for s in self.data_out if s.handles_error), UNUSED_VAR
        )
        stdout_var = next(
            (graph.get_link_var(self, s) for s in self.data_out if s.handles_stdout), UNUSED_VAR
        )
        stderr_var = next(
            (graph.get_link_var(self, s) for s in self.data_out if s.handles_stderr), UNUSED_VAR
        )

        return [
            cst.Assign(
                [
                    cst.AssignTarget(
                        cst.Tuple(
                            [
                                cst.Element(out_var),
                                cst.Element(stdout_var),
                                cst.Element(stderr_var),
                                cst.Element(error_var),
                            ]
                        )
                    )
                ],
                cst.Call(
                    cst_var(CALL_FUNCTION_UNSAFE_FUNC_ID)
                    if module_file.trusted
                    else cst_var(CALL_FUNCTION_SAFE_FUNC_ID),
                    [
                        cst.Arg(cst_str(module_name)),
                        cst.Arg(
                            cst_str(self.function_identifier)
                            if self.function_identifier
                            else cst_var("None")
                        ),
                        cst.Arg(cst_var(self.allow_error)),
                        *args,
                        *kwargs,
                    ],
                ),
            )
        ]


class LoopStep(Step[StepSocket]):
    type: Literal[StepType.LOOP]

    _pred_socket_alias: ClassVar[str] = "DATA.IN.PREDICATE"
    _body_socket_alias: ClassVar[str] = "CONTROL.OUT.BODY"

    subgraph_socket_aliases: ClassVar[set[str]] = {_pred_socket_alias, _body_socket_alias}
    required_control_io: ClassVar[tuple[Range, Range]] = ((0, 1), (1, 2))
    required_data_io: ClassVar[tuple[Range, Range]] = ((1, 1), (0, 0))

    def run(
        self, graph: "ComputeGraph", in_vars: dict[SocketId, ProgramVariable], *_
    ) -> ProgramFragment:
        pred_socket = self.alias_map.get(self._pred_socket_alias)
        pred_fragment = (
            [
                *self.run_subgraph(self._pred_socket_alias, graph).body,
                cst.If(test=in_vars[pred_socket.id], body=cst.SimpleStatementSuite([cst.Break()])),
            ]
            if pred_socket
            else []
        )
        return [
            cst.While(
                test=cst_var(True),
                body=cst.IndentedBlock(
                    [*pred_fragment, *self.run_subgraph(self._body_socket_alias, graph).body]
                ),
            )
        ]


class IfElseStep(Step[StepSocket]):
    type: Literal[StepType.IF_ELSE]

    _pred_socket_alias: ClassVar[str] = "DATA.IN.PREDICATE"
    _if_socket_alias: ClassVar[str] = "CONTROL.OUT.IF"
    _else_socket_alias: ClassVar[str] = "CONTROL.OUT.ELSE"

    subgraph_socket_aliases: ClassVar[set[str]] = {
        _pred_socket_alias,
        _if_socket_alias,
        _else_socket_alias,
    }
    required_control_io: ClassVar[tuple[Range, Range]] = ((0, 1), (2, 3))
    required_data_io: ClassVar[tuple[Range, Range]] = ((1, 1), (0, 0))

    def run(
        self, graph: "ComputeGraph", in_vars: dict[SocketId, ProgramVariable], *_
    ) -> ProgramFragment:
        def compile_control_flow(s_alias: str) -> cst.BaseSuite:
            return cst.IndentedBlock([*self.run_subgraph(s_alias, graph).body])

        return [
            *self.run_subgraph(self._pred_socket_alias, graph).body,
            cst.If(
                test=in_vars[self.alias_map[self._pred_socket_alias].id],
                body=compile_control_flow(self._if_socket_alias),
                orelse=cst.Else(compile_control_flow(self._else_socket_alias)),
            ),
        ]


StepClasses = (
    InputStep
    | OutputStep
    | PyRunFunctionStep
    | StringMatchStep
    | ObjectAccessStep
    | LoopStep
    | IfElseStep
)


class ComputeGraph(Graph[StepClasses, GraphEdge[str]]):  # type: ignore
    nodes: Sequence[Annotated[StepClasses, Field(discriminator="type")]]

    VAR_PREFIX: ClassVar[str] = "var_"

    _var_node_id_gen = PrivateAttr(default=count())
    _var_node_id_map: dict[str, int] = PrivateAttr(default={})

    _var_socket_id_gen: dict[str, count] = PrivateAttr(default=defaultdict(lambda: count()))
    _var_socket_id_map: dict[str, dict[str, int]] = PrivateAttr(default=defaultdict(dict))

    def get_link_var(self, from_node: Step, from_socket: StepSocket) -> ProgramVariable:
        uniq_node_id = self._var_node_id_map.setdefault(from_node.id, next(self._var_node_id_gen))
        uniq_socket_id = self._var_socket_id_map.setdefault(from_node.id, {}).setdefault(
            from_socket.id, next(self._var_socket_id_gen[from_node.id])
        )
        # Remove all special characters and replace spaces with underscores using regex
        socket_label = re.sub(r"[^a-zA-Z0-9_]", "", from_socket.label.replace(" ", "_"))
        node_label = STEP_TYPE_SHORTHANDS[from_node.type]

        var_name_str = f"{self.VAR_PREFIX}{'_'.join(map(str, [uniq_node_id, node_label, uniq_socket_id, socket_label]))}"
        return cst.Name(var_name_str.lower())

    def link_type(self, edge: GraphEdge[str]) -> SocketType:
        def get_socket_type(step: Step, socket: StepSocket) -> SocketType:
            # NOTE: Predicate sockets for `IfElseStep` take in data but are treated as control sockets
            if step.type == StepType.IF_ELSE and socket.alias == IfElseStep._pred_socket_alias:
                return SocketType.CONTROL
            return socket.type

        from_node, to_node = self.node_index.get(edge.from_node_id), self.node_index.get(edge.to_node_id)  # fmt: skip
        from_socket = from_node.get_socket(edge.from_socket_id) if from_node else None
        to_socket = to_node.get_socket(edge.to_socket_id) if to_node else None
        assert from_node and from_socket and to_node and to_socket

        from_socket_t, to_socket_t = get_socket_type(from_node, from_socket), get_socket_type(to_node, to_socket)  # fmt: skip
        # NOTE: As long as one of the sockets is a control socket, the link is considered a control link
        # This is because there can be a data socket connected to a control socket
        is_control = any(map(lambda t: t == SocketType.CONTROL, [from_socket_t, to_socket_t]))
        if from_socket._dir != to_socket._dir:
            return SocketType.CONTROL if is_control else SocketType.DATA
        raise ValueError(f"Invalid link: {from_socket.id} -> {to_socket.id}")

    def run(self, debug: bool = True, node_ids: set[str] | None = None) -> Program:
        """
        Run the compute graph with the given user input.

        Args:
            debug (bool, optional): Whether to include debug statements in the program. Defaults to True.
            node_ids (set[int], optional): The node ids to run. Defaults to None.

        Returns:
            Program: The program that is generated from the compute graph
        """
        # If node_ids is provided, we exclude all other nodes
        # This is useful when we want to run only a subset of the compute graph
        node_ids_to_exclude: set[str] = set()
        if node_ids is not None:
            node_ids_to_exclude = set(self.node_index.keys()) - node_ids

        subgraph_node_ids: set[str] = set()
        for node in filter(lambda n: n.id not in node_ids_to_exclude, self.nodes):
            subgraph_node_ids |= node.get_all_subgraph_node_ids(self)

        # We do not consider subgraph nodes when determining the flow order (topological order) of the main compute graph
        # The responsibility of determining the order of subgraph nodes is deferred to the step itself
        topo_order = self.topological_sort(subgraph_node_ids | node_ids_to_exclude)

        program_body: ProgramBody = []
        for _i, curr_node in enumerate(topo_order):
            # Output of a step will be stored in a variable in the format `var_{step_id}_{socket_id}`
            # It is assumed that every step will always output the same number of values as the number of output sockets
            # As such, all we need to do is to pass in the correct variables to the next step
            in_vars: dict[SocketId, ProgramVariable] = {}
            in_files: dict[SocketId, File] = {}

            for in_edge in self.in_edges_index[curr_node.id]:
                from_n = self.node_index[in_edge.from_node_id]
                from_s_lst = [out_ for out_ in from_n.outputs if out_.id == in_edge.from_socket_id]
                if (from_s := from_s_lst[0] if from_s_lst else None) is None:
                    continue

                if (to_s := curr_node.get_socket(in_edge.to_socket_id)) is None:
                    continue

                if from_s.data is not None and isinstance(from_s.data, File):
                    # NOTE: File objects are passed directly to the next step *AND* serialized as a variable (as a filepath)
                    in_files[to_s.id] = from_s.data

                in_vars[to_s.id] = self.get_link_var(from_n, from_s)

            curr_node._debug = debug
            program_body.extend(
                assemble_fragment(curr_node.run(self, in_vars, in_files), add_spacer=_i > 0)
            )

        return hoist_imports(cst.Module(body=program_body))
