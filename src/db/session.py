from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from db.models import Base
from settings import settings


class DatabaseManager:
    def __init__(self, url: str = settings.DATABASE_URL) -> None:
        self.url = url
        self.engine = create_async_engine(url)
        self.session_factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def create_tables(self) -> None:
        database_url = make_url(self.url)
        if database_url.get_backend_name() == "sqlite" and database_url.database not in (None, ":memory:"):
            Path(database_url.database).parent.mkdir(parents=True, exist_ok=True)
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    @asynccontextmanager
    async def get_session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory.begin() as session:
            yield session

    async def close(self) -> None:
        await self.engine.dispose()


db_manager = DatabaseManager()
