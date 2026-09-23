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

    async def remember_many(self, chat_id: int, users: Iterable[User]) -> None:
        async with self.database.get_session() as session:
            repo = UserRepository(session)
            for user in users:
                await repo.remember(chat_id, user)

    async def random_user(self, chat_id: int, sender: User | None) -> GroupUser | None:
        async with self.database.get_session() as session:
            repo = UserRepository(session)
            if sender is not None:
                await repo.remember(chat_id, sender)
            return await repo.random_user(
                chat_id, excluded_user_id=sender.id if sender is not None else None
            )

    async def next_queued_user(
        self, chat_id: int, sender: User | None
    ) -> GroupUser | None:
        async with self.database.get_session() as session:
            repo = UserRepository(session)
            if sender is not None:
                await repo.remember(chat_id, sender)
            return await repo.next_queued_user(
                chat_id, excluded_user_id=sender.id if sender is not None else None
            )

    async def set_participation(
        self, chat_id: int, sender: User, target: User, excluded: bool
    ) -> bool:
        async with self.database.get_session() as session:
            repo = UserRepository(session)
            await repo.remember(chat_id, sender)
            if target.id != sender.id:
                await repo.remember(chat_id, target)
            return await repo.set_excluded(chat_id, target.id, excluded)

    async def set_participation_by_username(
        self, chat_id: int, sender: User, username: str, excluded: bool
    ) -> GroupUser | None:
        async with self.database.get_session() as session:
            repo = UserRepository(session)
            await repo.remember(chat_id, sender)
            target = await repo.get_by_username(chat_id, username)
            if target is None or not target.is_active:
                return None
            if not await repo.set_excluded(chat_id, target.user_id, excluded):
                return None
            return target

    async def set_participation_for_user(
        self, chat_id: int, user_id: int, excluded: bool
    ) -> GroupUser | None:
        async with self.database.get_session() as session:
            repo = UserRepository(session)
            user = await repo.get_user(chat_id, user_id)
            if user is None or not user.is_active:
                return None
            if not await repo.set_excluded(chat_id, user_id, excluded):
                return None
            return user

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

    async def get_user_by_username(
        self, chat_id: int, username: str
    ) -> GroupUser | None:
        async with self.database.get_session() as session:
            return await UserRepository(session).get_by_username(chat_id, username)

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

    async def update_user_by_username(
        self,
        chat_id: int,
        current_username: str,
        first_name: str,
        new_username: str,
    ) -> bool:
        async with self.database.get_session() as session:
            repo = UserRepository(session)
            user = await repo.get_by_username(chat_id, current_username)
            if user is None:
                return False
            return await repo.update_details(chat_id, user.user_id, first_name, new_username)

    async def delete_user(self, chat_id: int, user_id: int) -> bool:
        async with self.database.get_session() as session:
            return await UserRepository(session).delete_user(chat_id, user_id)


user_service = UserService(db_manager)
