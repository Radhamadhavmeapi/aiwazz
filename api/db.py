"""Database engine + session handling (SQLAlchemy 2 async; MariaDB via aiomysql, SQLite in tests)."""
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    """Naive UTC (MariaDB DATETIME has no time zone; everything is stored in UTC)."""
    return datetime.now(UTC).replace(tzinfo=None)


def make_engine(url: str) -> AsyncEngine:
    if not url:
        raise RuntimeError("AIWAZZ_DATABASE_URL is not set (see api/.env.example)")
    kwargs = {"pool_pre_ping": True, "pool_recycle": 1800} if url.startswith("mysql") else {}
    return create_async_engine(url, **kwargs)


def make_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessionmaker() as session:
        yield session
