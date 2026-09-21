from aiogram import Router
from aiogram.types import ChatMemberUpdated, Message

from handler.common import GROUP_TYPES, is_group, sender
from service.membership import is_active_member
from service.users import user_service


router = Router(name="events")


@router.message()
async def observe_message(message: Message) -> None:
    if not is_group(message):
        return
    await user_service.observe_message(
        message.chat.id,
        sender(message),
        message.new_chat_members or [],
        message.left_chat_member.id if message.left_chat_member else None,
    )


@router.chat_member()
async def observe_membership(event: ChatMemberUpdated) -> None:
    if event.chat.type not in GROUP_TYPES:
        return
    user = event.new_chat_member.user
    if user.is_bot:
        return
    await user_service.observe_membership(
        event.chat.id, user, is_active_member(event.new_chat_member)
    )
