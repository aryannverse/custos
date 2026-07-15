utf-8from pydantic import BaseModel, Field
from typing import Any


class ForeignKeyDef(BaseModel):
    referred_table: str
    referred_column: str


class ColumnDef(BaseModel):
    name: str
    type: str
    primary_key: bool = False
    foreign_key: ForeignKeyDef | None = None
    sample_values: list[Any] = Field(default_factory=list)
    description: str | None = None


class TableDef(BaseModel):
    name: str
    columns: dict[str, ColumnDef]
    description: str | None = None


class DatabaseSchema(BaseModel):
    tables: dict[str, TableDef]
