from html import escape

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from handler.common import is_group, remember_sender, sender
from repository.user_repository import AmbiguousUsernameError
from service.membership import is_active_member
from service.usernames import parse_username
from service.users import user_service


router = Router(name="commands")
HELP = (
    "Добавьте меня в группу. Команды в группе:\n"
    "/random — выбрать случайного участника\n"
    "/exclude @username — исключить участника из выбора\n"
    "/include @username — вернуть участника в выбор\n"
    "/admin — управление списком\n"
    "Username можно посмотреть через /admin → Список. Команды также работают "
    "ответом на сообщение; без имени или ответа они меняют ваше участие."
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
        await message.answer("Пока нет других участников для выбора.")
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
    text = message.text or message.caption or ""
    arguments = text.split(maxsplit=1)
    username: str | None = None
    if len(arguments) == 2:
        username = parse_username(arguments[1])
        if username is None:
            await message.answer("Укажите @username участника или ответьте на его сообщение.")
            return
    target = actor
    reply = message.reply_to_message
    if reply is not None and username is None:
        target = sender(reply)
        if target is None:
            await message.answer("Ответьте на сообщение человека.")
            return
        target_member = await message.bot.get_chat_member(message.chat.id, target.id)
        if not is_active_member(target_member):
            await message.answer("Этот пользователь больше не состоит в группе.")
            return
    if username is not None:
        try:
            selected = await user_service.set_participation_by_username(
                message.chat.id, actor, username, excluded
            )
        except AmbiguousUsernameError:
            await message.answer("В базе несколько записей с этим @username. Уточните данные в панели.")
            return
        if selected is None:
            await message.answer("Участник с таким @username не найден в активном списке этой группы.")
            return
        name = selected.first_name
    else:
        changed = await user_service.set_participation(
            message.chat.id, actor, target, excluded
        )
        if not changed:
            await message.answer("Участник не найден в списке.")
            return
        name = target.first_name
    action = "исключён из выбора" if excluded else "снова участвует в выборе"
    await message.answer(f"{escape(name)} {action}.")


@router.message(Command("exclude"))
async def exclude(message: Message) -> None:
    await change_participation(message, True)


@router.message(Command("include"))
async def include(message: Message) -> None:
    await change_participation(message, False)
