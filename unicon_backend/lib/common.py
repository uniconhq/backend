import copy
from typing import Any, ClassVar, Generic, TypeVar

from pydantic_core import PydanticUndefined
from sqlalchemy.orm.session import Session
from sqlalchemy.sql import select
from sqlmodel import MetaData, SQLModel

from unicon_backend.database import SessionLocal
from unicon_backend.lib.helpers import instance_in

_T = TypeVar("_T", bound="CustomSQLModel")


class CustomSQLModel(SQLModel, Generic[_T]):
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_`%(constraint_name)s`",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )

    excluded_fields_on_copy: ClassVar[list[str]] = []

    def excluded_on_copy(self) -> bool:
        return False

    def shallow_copy(self: _T) -> _T:
        data = {}
        for name, info in self.model_fields.items():
            value = getattr(self, name)
            if (
                getattr(info, "primary_key", PydanticUndefined) != PydanticUndefined
                or getattr(info, "foreign_key", PydanticUndefined) != PydanticUndefined
                or name in self.excluded_fields_on_copy
            ):
                continue
            data[name] = copy.copy(value)
        return self.__class__(**data)

    def deep_copy(self: _T, excluded_classes: list[Any] | None = None) -> _T:
        excluded_classes = excluded_classes or []
        child_excluded_classes = excluded_classes + [self.__class__]  # avoid infinite recursion

        copied = self.shallow_copy()

        def _allowed_to_copy(value):
            return not instance_in(value, excluded_classes) and not value.excluded_on_copy()

        for name in self.__sqlmodel_relationships__:
            value = getattr(self, name)

            if name in self.excluded_fields_on_copy:
                continue

            if isinstance(value, CustomSQLModel) and _allowed_to_copy(value):
                setattr(copied, name, value.deep_copy(excluded_classes=child_excluded_classes))

            elif isinstance(value, list):
                children = []
                for item in value:
                    if not _allowed_to_copy(item):
                        continue
                    if isinstance(item, CustomSQLModel):
                        child = item.deep_copy(excluded_classes=child_excluded_classes)
                    else:
                        child = copy.deepcopy(item)
                    children.append(child)
                setattr(copied, name, children)

        return copied

    @classmethod
    def get_by_pk(cls: type[_T], id: int | dict[str, int], db_session: Session | None = None) -> _T:
        pk_fields = [
            name
            for name, field in cls.model_fields.items()
            if getattr(field, "primary_key", PydanticUndefined) != PydanticUndefined
        ]

        if len(pk_fields) == 1:
            conditions = [getattr(cls, pk_fields[0]) == id]
        else:
            if not isinstance(id, dict):
                raise ValueError(f"Composite primary key requires dict, got {type(id)}")

            if set(id.keys()) != set(pk_fields):
                raise ValueError(f"Invalid primary keys. Required: {list(pk_fields)}")

            conditions = [getattr(cls, name) == id[name] for name in pk_fields]

        def _get_model_by_pk(db_session: Session) -> _T:
            result = db_session.scalar(select(cls).where(*conditions))
            if result is None:
                raise ValueError(f"{cls.__name__} with id {id} not found")
            return result

        if db_session is not None:
            return _get_model_by_pk(db_session)

        with SessionLocal() as db_session:
            return _get_model_by_pk(db_session)
