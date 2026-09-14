"""Running Alembic from code. Start-up, CI and the tests all move a database to
the latest revision and none has an `alembic.ini` to point at.
"""

from alembic import command
from alembic.config import Config

PACKAGE_LOCATION = "unicon:db/alembic"


def alembic_config(database_url: str) -> Config:
    config = Config()
    config.set_main_option("script_location", PACKAGE_LOCATION)
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def upgrade_to_head(database_url: str) -> None:
    command.upgrade(alembic_config(database_url), "head")


def downgrade_to_base(database_url: str) -> None:
    """Only the tests use this; a deployment rolls forward."""
    command.downgrade(alembic_config(database_url), "base")
