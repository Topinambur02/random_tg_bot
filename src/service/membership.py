from aiogram.enums import ChatMemberStatus
from aiogram.types import ChatMember


def is_active_member(member: ChatMember) -> bool:
    if member.status == ChatMemberStatus.RESTRICTED:
        return member.is_member
    return member.status in {
        ChatMemberStatus.CREATOR,
        ChatMemberStatus.ADMINISTRATOR,
        ChatMemberStatus.MEMBER,
    }
