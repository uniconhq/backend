"""Server time, the only clock the UI trusts."""

from datetime import datetime

from pydantic import BaseModel


class ServerTime(BaseModel):
    now: datetime
