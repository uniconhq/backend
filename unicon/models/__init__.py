"""The nine tables Unicon owns. Importing this package imports every table, which
is what Alembic's autogenerate needs to see the whole schema.
"""

from unicon.models.entrant_repos import EntrantRepo
from unicon.models.judging import Judging
from unicon.models.jupyter import JupyterSession
from unicon.models.participation import Invite, Participant, Team, TeamMember
from unicon.models.sessions import Session
from unicon.models.uploads import Upload

__all__ = [
    "EntrantRepo",
    "Invite",
    "Judging",
    "JupyterSession",
    "Participant",
    "Session",
    "Team",
    "TeamMember",
    "Upload",
]
