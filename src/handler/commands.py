from html import escape

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from handler.common import is_group, remember_sender, sender
from service.membership import is_active_member
from service.users import user_service


router = Router(name="commands")
HELP = (
    "Добавьте меня в группу. Команды в группе:\n"
    "/random — выбрать случайного участника\n"
    "/exclude — исключить себя из выбора\n"
    "/include — снова участвовать\n"
    "/admin — управление списком\n"
    "Любой участник может ответить на сообщение другого командой "
    "/exclude или /include, чтобы изменить его участие."
)


@router.message(CommandStart())
async def start(message: Message) -> None:
    await remember_sender(message)
    await message.answer(HELP)


@router.message(Command("random"))
async def random_person(message: Message) -> None:
    if not is_group(message):
        await message.answer("Команда работает только в группе.")
        return
    person = await user_service.random_user(message.chat.id, sender(message))
    if person is None:
        await message.answer("Пока нет участников для выбора.")
        return
    name = escape(person.first_name)
    await message.answer(
        f'Случайный участник: <a href="tg://user?id={person.user_id}">{name}</a>'
    )


async def change_participation(message: Message, excluded: bool) -> None:
    if not is_group(message):
        await message.answer("Команда работает только в группе.")
        return
    actor = sender(message)
    if actor is None:
        await message.answer("Не удалось определить пользователя.")
        return
    target = actor
    reply = message.reply_to_message
    if reply is not None:
        target = sender(reply)
        if target is None:
            await message.answer("Ответьте на сообщение человека.")
            return
        target_member = await message.bot.get_chat_member(message.chat.id, target.id)
        if not is_active_member(target_member):
            await message.answer("Этот пользователь больше не состоит в группе.")
            return
    changed = await user_service.set_participation(
        message.chat.id, actor, target, excluded
    )
    if not changed:
        await message.answer("Участник не найден в списке.")
        return
    action = "исключён из выбора" if excluded else "снова участвует в выборе"
    await message.answer(f"{escape(target.first_name)} {action}.")


@router.message(Command("exclude"))
async def exclude(message: Message) -> None:
    await change_participation(message, True)


@router.message(Command("include"))
async def include(message: Message) -> None:
    await change_participation(message, False)
