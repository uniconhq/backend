"""Who is making this request. The session row itself never leaves `services/`;
this is what the rest of the code passes around, and it holds nothing secret.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ActiveSession:
    id: bytes

    user_id: int
    username: str
    created_at: datetime
