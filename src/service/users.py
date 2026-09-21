from collections.abc import Iterable

from aiogram.types import User

from db.models import GroupUser
from db.session import DatabaseManager, db_manager
from repository.user_repository import UserRepository


class UserService:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    async def remember(self, chat_id: int, user: User) -> None:
        async with self.database.get_session() as session:
            await UserRepository(session).remember(chat_id, user)

    async def random_user(self, chat_id: int, sender: User | None) -> GroupUser | None:
        async with self.database.get_session() as session:
            repo = UserRepository(session)
            if sender is not None:
                await repo.remember(chat_id, sender)
            return await repo.random_user(chat_id)

    async def set_participation(
        self, chat_id: int, sender: User, target: User, excluded: bool
    ) -> bool:
        async with self.database.get_session() as session:
            repo = UserRepository(session)
            await repo.remember(chat_id, sender)
            if target.id != sender.id:
                await repo.remember(chat_id, target)
            return await repo.set_excluded(chat_id, target.id, excluded)

    async def observe_message(
        self,
        chat_id: int,
        sender: User | None,
        new_members: Iterable[User],
        left_user_id: int | None,
    ) -> None:
        async with self.database.get_session() as session:
            repo = UserRepository(session)
            if sender is not None:
                await repo.remember(chat_id, sender)
            for user in new_members:
                await repo.remember(chat_id, user)
            if left_user_id is not None:
                await repo.mark_left(chat_id, left_user_id)

    async def observe_membership(self, chat_id: int, user: User, active: bool) -> None:
        async with self.database.get_session() as session:
            repo = UserRepository(session)
            if active:
                await repo.remember(chat_id, user)
            else:
                await repo.mark_left(chat_id, user.id)

    async def list_page(
        self, chat_id: int, page: int, page_size: int
    ) -> tuple[int, int, list[GroupUser]]:
        async with self.database.get_session() as session:
            repo = UserRepository(session)
            count = await repo.count_users(chat_id)
            page = min(page, max(0, (count - 1) // page_size))
            users = await repo.list_users(chat_id, page * page_size, page_size)
            return count, page, users

    async def get_user(self, chat_id: int, user_id: int) -> GroupUser | None:
        async with self.database.get_session() as session:
            return await UserRepository(session).get_user(chat_id, user_id)

    async def add_user(
        self, chat_id: int, user_id: int, first_name: str, username: str | None
    ) -> bool:
        async with self.database.get_session() as session:
            return await UserRepository(session).add_manual(
                chat_id, user_id, first_name, username
            )

    async def update_user(
        self, chat_id: int, user_id: int, first_name: str, username: str | None
    ) -> bool:
        async with self.database.get_session() as session:
            return await UserRepository(session).update_details(
                chat_id, user_id, first_name, username
            )

    async def delete_user(self, chat_id: int, user_id: int) -> bool:
        async with self.database.get_session() as session:
            return await UserRepository(session).delete_user(chat_id, user_id)


user_service = UserService(db_manager)
