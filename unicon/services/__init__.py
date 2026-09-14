"""Use cases: the only place that writes to the database or calls `forge/`. A
service returns a schema, never an ORM object, so a router cannot lazily load
half the database while serialising a response.
"""
