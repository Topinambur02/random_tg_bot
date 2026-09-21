from aiogram.enums import ChatType
from aiogram.types import Message, User

from service.users import user_service


GROUP_TYPES = {ChatType.GROUP, ChatType.SUPERGROUP}


def is_group(message: Message) -> bool:
    return message.chat.type in GROUP_TYPES


def sender(message: Message) -> User | None:
    if message.sender_chat is not None or message.from_user is None:
        return None
    if message.from_user.is_bot:
        return None
    return message.from_user


async def remember_sender(message: Message) -> None:
    user = sender(message)
    if is_group(message) and user is not None:
        await user_service.remember(message.chat.id, user)
