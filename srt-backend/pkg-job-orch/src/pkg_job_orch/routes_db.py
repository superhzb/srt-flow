"""Database introspection routes for development tooling."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import delete, func
from sqlmodel import Session, SQLModel, col, select

from .db import session_scope
from .models import Job, User
from .orchestration import seed_dev_user

__all__ = ["router"]

router = APIRouter(prefix="/db", tags=["db"])

TABLES: dict[str, type[SQLModel]] = {
    "user": User,
    "job": Job,
}

DELETE_ORDER: tuple[type[SQLModel], ...] = (Job, User)


def _table_or_404(name: str) -> type[SQLModel]:
    table = TABLES.get(name)
    if table is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"unknown table: {name}",
        )
    return table


JsonValue = object | None


def _count(session: Session, table: type[SQLModel]) -> int:
    stmt = select(func.count()).select_from(table)
    return int(session.exec(stmt).one())


def _columns(table: type[SQLModel]) -> list[str]:
    return list(table.model_fields.keys())


def _pk_column(table: type[SQLModel]) -> object:
    if table is User:
        return User.id
    return Job.id


def _json_value(value: object | None) -> JsonValue:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _row_dict(row: SQLModel, columns: list[str]) -> dict[str, JsonValue]:
    return {column: _json_value(getattr(row, column)) for column in columns}


@router.get("/tables")
async def list_tables() -> list[dict[str, int | str]]:
    with session_scope() as session:
        return [{"name": name, "count": _count(session, table)} for name, table in TABLES.items()]


@router.get("/tables/{name}")
async def get_table_rows(
    name: str,
    page: int = Query(default=0, ge=0),
    size: int = Query(default=20, ge=1, le=100),
) -> dict[str, object]:
    table = _table_or_404(name)
    columns = _columns(table)
    offset = page * size
    with session_scope() as session:
        total = _count(session, table)
        stmt = select(table).order_by(col(_pk_column(table))).offset(offset).limit(size)
        rows = [_row_dict(row, columns) for row in session.exec(stmt).all()]
    return {
        "columns": columns,
        "rows": rows,
        "total": total,
        "page": page,
        "size": size,
    }


@router.post("/clear")
async def clear_all_data() -> dict[str, int]:
    cleared = 0
    with session_scope() as session:
        for table in DELETE_ORDER:
            cleared += _count(session, table)
            session.exec(delete(table))
        seed_dev_user(session)
    return {"cleared": cleared}
