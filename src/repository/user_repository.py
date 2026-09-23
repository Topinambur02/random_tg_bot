from aiogram.types import User
from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import GroupUser


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def remember(self, chat_id: int, user: User) -> None:
        if user.is_bot:
            return
        statement = insert(GroupUser).values(
            chat_id=chat_id,
            user_id=user.id,
            first_name=user.first_name,
            username=user.username,
            is_active=True,
            is_excluded=False,
        )
        await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=[GroupUser.chat_id, GroupUser.user_id],
                set_={
                    "is_active": True,
                    "username": statement.excluded.username,
                },
            )
        )

    async def get_by_username(self, chat_id: int, username: str) -> GroupUser | None:
        result = await self.session.scalars(
            select(GroupUser)
            .where(
                GroupUser.chat_id == chat_id,
                func.lower(GroupUser.username) == username.lower(),
            )
            .limit(2)
        )
        users = list(result)
        if len(users) > 1:
            raise AmbiguousUsernameError(username)
        return users[0] if users else None

    async def _ensure_username_available(
        self, chat_id: int, user_id: int, username: str | None
    ) -> None:
        if username is None:
            return
        existing = await self.get_by_username(chat_id, username)
        if existing is not None and existing.user_id != user_id:
            raise UsernameInUseError(username)

    async def add_manual(
        self, chat_id: int, user_id: int, first_name: str, username: str | None
    ) -> bool:
        await self._ensure_username_available(chat_id, user_id, username)
        statement = insert(GroupUser).values(
            chat_id=chat_id,
            user_id=user_id,
            first_name=first_name,
            username=username,
            is_active=True,
            is_excluded=False,
        )
        result = await self.session.execute(
            statement.on_conflict_do_update(
                index_elements=[GroupUser.chat_id, GroupUser.user_id],
                set_={
                    "first_name": statement.excluded.first_name,
                    "username": statement.excluded.username,
                    "is_active": True,
                },
                where=GroupUser.is_active.is_(False),
            )
        )
        return result.rowcount > 0

    async def update_details(
        self, chat_id: int, user_id: int, first_name: str, username: str | None
    ) -> bool:
        await self._ensure_username_available(chat_id, user_id, username)
        result = await self.session.execute(
            update(GroupUser)
            .where(GroupUser.chat_id == chat_id, GroupUser.user_id == user_id)
            .values(first_name=first_name, username=username)
        )
        return result.rowcount > 0

    async def delete_user(self, chat_id: int, user_id: int) -> bool:
        result = await self.session.execute(
            delete(GroupUser).where(
                GroupUser.chat_id == chat_id, GroupUser.user_id == user_id
            )
        )
        return result.rowcount > 0

    async def get_user(self, chat_id: int, user_id: int) -> GroupUser | None:
        return await self.session.get(GroupUser, (chat_id, user_id))

    async def list_users(self, chat_id: int, offset: int, limit: int) -> list[GroupUser]:
        result = await self.session.scalars(
            select(GroupUser)
            .where(GroupUser.chat_id == chat_id)
            .order_by(GroupUser.first_name, GroupUser.user_id)
            .offset(offset)
            .limit(limit)
        )
        return list(result)

    async def count_users(self, chat_id: int) -> int:
        return await self.session.scalar(
            select(func.count()).select_from(GroupUser).where(GroupUser.chat_id == chat_id)
        ) or 0

    async def mark_left(self, chat_id: int, user_id: int) -> None:
        await self.session.execute(
            update(GroupUser)
            .where(GroupUser.chat_id == chat_id, GroupUser.user_id == user_id)
            .values(is_active=False)
        )

    async def set_excluded(self, chat_id: int, user_id: int, excluded: bool) -> bool:
        result = await self.session.execute(
            update(GroupUser)
            .where(
                GroupUser.chat_id == chat_id,
                GroupUser.user_id == user_id,
                GroupUser.is_active.is_(True),
            )
            .values(is_excluded=excluded)
        )
        return result.rowcount > 0

    async def random_user(
        self, chat_id: int, excluded_user_id: int | None = None
    ) -> GroupUser | None:
        conditions = [
            GroupUser.chat_id == chat_id,
            GroupUser.is_active.is_(True),
            GroupUser.is_excluded.is_(False),
        ]
        if excluded_user_id is not None:
            conditions.append(GroupUser.user_id != excluded_user_id)
        return await self.session.scalar(
            select(GroupUser)
            .where(*conditions)
            .order_by(func.random())
            .limit(1)
        )


class AmbiguousUsernameError(LookupError):
    pass


class UsernameInUseError(ValueError):
    pass
