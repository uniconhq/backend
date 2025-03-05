import json
from datetime import datetime, timedelta
from typing import Annotated

import typer
from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table
from sqlalchemy import select
from sqlmodel import col

rich_console = Console()

app = typer.Typer(name="Unicon 🦄 CLI")

permify_app = typer.Typer()
app.add_typer(permify_app, name="permify", help="Initialize and seed permissions")


@permify_app.command(name="init")
def init_perms_schema(
    schema_file: Annotated[
        typer.FileText | None,
        typer.Argument(
            help="If not provided, the default schema file ('unicon.perm') will be used"
        ),
    ] = None,
) -> None:
    """Initializes permission schema"""
    import importlib.resources

    import permify as p
    from permify.exceptions import NotFoundException

    from unicon_backend.constants import PERMIFY_HOST, PERMIFY_TENANT_ID

    schema: str = (
        schema_file.read()
        if schema_file
        else importlib.resources.files("unicon_backend").joinpath("unicon.perm").read_text()
    )

    if (schema_write_body := p.SchemaWriteBody.from_dict({"schema": schema})) is None:
        # This should never happen, there is no validation/parsing done on the schema
        raise ValueError("Failed to create schema payload!")

    rich_console.print(f"Permify Host: [bold blue]{PERMIFY_HOST}[/bold blue]")

    schema_api = p.SchemaApi(p.ApiClient(p.Configuration(host=PERMIFY_HOST)))

    try:
        # NOTE: 10 is an arbitrary page size chosen
        # We assume that the current schema, it there is one, is within the first 10 schemas
        existing_schemas = schema_api.schemas_list(
            PERMIFY_TENANT_ID, p.SchemaListBody(page_size=10)
        )
        if curr_schema_v := existing_schemas.head:
            assert existing_schemas.schemas is not None
            curr_schema = next(s for s in existing_schemas.schemas if s.version == curr_schema_v)
            rich_console.print(
                f"Current schema version: [bold red]{curr_schema_v}[/bold red] ({curr_schema.created_at})"
            )
            typer.confirm(
                "Are you sure you want to overwrite and invalidate this schema?", abort=True
            )
    except NotFoundException:
        rich_console.print("No existing schema found, initializing new schema...")

    write_resp = schema_api.schemas_write(PERMIFY_TENANT_ID, schema_write_body)
    if (schema_version := write_resp.schema_version) is None:
        raise ValueError("Failed to create schema, is the schema valid?")

    rich_console.print(f"Initialized schema version: [bold green]{schema_version}[/bold green] 🥳")
    rich_console.print(
        "If you like update permissions for existing records in the database, run: [bold magenta]permify seed[/bold magenta]"
    )


@permify_app.command(name="seed")
def seed_perms():
    """Add permission tuples for all existing records in the database. Existing tuples will be cleared."""
    import permify as p

    from unicon_backend.constants import PERMIFY_HOST, PERMIFY_TENANT_ID

    rich_console.print(f"Permify Host: [bold blue]{PERMIFY_HOST}[/bold blue]")

    schema_api = p.SchemaApi(p.ApiClient(p.Configuration(host=PERMIFY_HOST)))
    existing_schemas = schema_api.schemas_list(PERMIFY_TENANT_ID, p.SchemaListBody())
    if not existing_schemas.head:
        rich_console.print(
            "No schema found, please initialize a schema first. Run: [bold magenta]permify init[/bold magenta]"
        )

    from sqlalchemy import select

    from unicon_backend.database import SessionLocal
    from unicon_backend.lib.permissions import delete_all_permission_records, permission_create
    from unicon_backend.models.file import FileORM
    from unicon_backend.models.links import UserRole
    from unicon_backend.models.organisation import Group, Organisation, Project, Role
    from unicon_backend.models.problem import ProblemORM, SubmissionORM

    rich_console.print(f"Current schema version: [bold red]{existing_schemas.head}[/bold red]")
    typer.confirm("Are you sure you want to remove all existing permission tuples?", abort=True)
    delete_all_permission_records()

    rich_console.print("Seeding new permissions under the current schema...")
    model_classes = [Project, Role, ProblemORM, SubmissionORM, UserRole, Organisation, Group, FileORM]  # fmt: off
    with SessionLocal() as session:
        for model_class in model_classes:
            models = session.scalars(select(model_class)).all()
            for model in models:
                permission_create(model)
            rich_console.print(
                f"[bold magenta]{model_class.__name__}[/bold magenta] (count: {len(models)})"
            )
    rich_console.print("Permissions seeded successfully 🌈")


@app.command(name="seed")
def seed(username: str, password: str, problem_defns: list[typer.FileText]):
    """Seed the database with sample data"""
    from unicon_backend.database import SessionLocal
    from unicon_backend.dependencies.auth import AUTH_PWD_CONTEXT
    from unicon_backend.dependencies.project import role_permissions
    from unicon_backend.evaluator.problem import Problem
    from unicon_backend.models.organisation import Organisation, Project, Role
    from unicon_backend.models.problem import ProblemORM
    from unicon_backend.models.user import UserORM

    db_session = SessionLocal()
    hash_password = AUTH_PWD_CONTEXT.hash(password)

    admin_user = db_session.scalar(select(UserORM).where(col(UserORM.username) == username))
    if admin_user:
        typer.confirm("User already exists. Add data to existing user?", abort=True)
    else:
        admin_user = UserORM(username=username, password=hash_password)
        db_session.add(admin_user)
        db_session.flush()

    organisation = Organisation(name="Unicon", description="Rainbows", owner_id=admin_user.id)

    loaded_problem_defns = [json.loads(problem_defn.read()) for problem_defn in problem_defns]
    for problem_defn in loaded_problem_defns:
        problem_defn["started_at"] = datetime.now()
        problem_defn["ended_at"] = datetime.now() + timedelta(weeks=2)
        problem_defn["closed_at"] = datetime.now() + timedelta(weeks=3)

    project = Project(
        name="Sparkles",
        organisation=organisation,
        problems=[
            ProblemORM.from_problem(Problem.model_validate(problem_defn))
            for problem_defn in loaded_problem_defns
        ],
    )
    project.roles = [
        Role(
            name="admin",
            users=[admin_user],
            **{perm: True for perm in role_permissions["admin"]},
        ),
        *[
            Role(name=role, **{perm: True for perm in role_permissions[role]})
            for role in ["helper", "member"]
        ],
    ]

    db_session.add_all([organisation, project])
    db_session.commit()

    rich_console.print("Database seeded successfully 🌈")

    table = Table(show_header=True, show_lines=True)
    table.add_column("Entity", style="cyan bold", no_wrap=True)
    table.add_column("Details", style="white")
    # fmt: off
    table.add_row("User", f"{admin_user.username} (id: {admin_user.id})")
    table.add_row("Organisation", f"{organisation.name} (id: {organisation.id})")
    table.add_row("Project", f"{project.name} (id: {project.id})")
    table.add_row("Roles", "\n".join(role.name for role in project.roles))
    table.add_row("Problems", "\n".join(f"{problem.name} (id: {problem.id})" for problem in project.problems))
    # fmt: on

    rich_console.print(table)


@app.command(name="assemble")
def assemble(defn_file: Annotated[typer.FileText, typer.Option("--defn", mode="r")]):
    """Assemble all programming tasks in provided problem definition"""
    from unicon_backend.evaluator.problem import Problem, ProgrammingTask
    from unicon_backend.models.problem import TaskType

    defn = Problem.model_validate_json(defn_file.read())
    for task in defn.tasks:
        if task.type != TaskType.PROGRAMMING:
            continue

        assert isinstance(task, ProgrammingTask)

        table = Table(title=f"Task #{task.id} Assembled Programs")
        table.add_column("Testcase ID", style="magenta")
        table.add_column("Program", style="green")

        # NOTE: We use the templates to generate the input step
        # This is so that we do not need to take in any user input and can simply assemble
        # the task directly from the given definition for a quick test
        for testcase in task.testcases:
            testcase.attach_user_inputs(task.required_inputs)
            assembled_prog = testcase.run()

            syntax_highlighted_code = Syntax(
                assembled_prog.code, "python", theme="material", line_numbers=True, word_wrap=True
            )
            table.add_row(str(testcase.id), syntax_highlighted_code)

        rich_console.print(table)


if __name__ == "__main__":
    app()
