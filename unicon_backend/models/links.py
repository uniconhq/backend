"""
This file exists because of the otherwise existing circular dependency between user and role files for the link_model.
"""

from sqlmodel import Field

from unicon_backend.lib.common import CustomSQLModel


class UserRole(CustomSQLModel, table=True):
    __tablename__ = "user_role"

    user_id: int = Field(foreign_key="user.id", primary_key=True)
    role_id: int = Field(foreign_key="role.id", primary_key=True)


class GroupMember(CustomSQLModel, table=True):
    __tablename__ = "group_member"

    user_id: int = Field(foreign_key="user.id", primary_key=True)
    group_id: int = Field(foreign_key="group.id", primary_key=True)


class GroupSupervisor(CustomSQLModel, table=True):
    __tablename__ = "group_supervisor"

    user_id: int = Field(foreign_key="user.id", primary_key=True)
    group_id: int = Field(foreign_key="group.id", primary_key=True)
