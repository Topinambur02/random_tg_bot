from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from handler.common import GROUP_TYPES, is_group, remember_sender, sender
from repository.user_repository import AmbiguousUsernameError
from service.membership import is_active_member
from service.usernames import parse_username
from service.users import user_service


router = Router(name="commands")
QUEUE_PAGE_SIZE = 20
HELP = (
    "Добавьте меня в группу. Команды в группе:\n"
    "/random — выбрать случайного участника\n"
    "/queue — показать текущую очередь\n"
    "/queue_next — выбрать следующего участника по очереди\n"
    "/exclude @username — исключить участника из выбора\n"
    "/include @username — вернуть участника в выбор\n"
    "/queue_exclude @username — исключить участника из очереди\n"
    "/queue_include @username — вернуть участника в очередь\n"
    "/admin — управление списком\n"
    "Username можно посмотреть через /admin → Участники. Команды также работают "
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
        await message.answer(
            "Сейчас нет доступных участников для выбора. "
            "Проверьте исключения или дождитесь окончания двухчасового перерыва."
        )
        return
    name = escape(person.first_name)
    await message.answer(
        f'Случайный участник: <a href="tg://user?id={person.user_id}">{name}</a>'
    )


async def queue_view(
    chat_id: int, page: int
) -> tuple[str, InlineKeyboardMarkup | None]:
    users = await user_service.queued_users(chat_id)
    if not users:
        return "Очередь пуста.", None

    last_page = (len(users) - 1) // QUEUE_PAGE_SIZE
    page = min(max(0, page), last_page)
    start = page * QUEUE_PAGE_SIZE
    lines = [f"Текущая очередь: {len(users)} чел. Страница {page + 1}/{last_page + 1}."]
    for position, user in enumerate(
        users[start:start + QUEUE_PAGE_SIZE], start=start + 1
    ):
        if user.username:
            label = f"@{escape(user.username)}"
        else:
            label = (
                f'<a href="tg://user?id={user.user_id}">{escape(user.first_name)}</a> '
                "(без @username)"
            )
        lines.append(f"{position}. {label}")

    navigation = []
    if page > 0:
        navigation.append(InlineKeyboardButton(
            text="←", callback_data=f"queue:list:{page - 1}"
        ))
    if page < last_page:
        navigation.append(InlineKeyboardButton(
            text="→", callback_data=f"queue:list:{page + 1}"
        ))
    markup = (
        InlineKeyboardMarkup(inline_keyboard=[navigation]) if navigation else None
    )
    return "\n".join(lines), markup


@router.message(Command("queue"))
async def show_queue(message: Message) -> None:
    if not is_group(message):
        await message.answer("Команда работает только в группе.")
        return
    await remember_sender(message)
    text, markup = await queue_view(message.chat.id, 0)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("queue:list:"))
async def show_queue_page(query: CallbackQuery) -> None:
    if query.message is None or query.message.chat.type not in GROUP_TYPES:
        await query.answer("Очередь доступна только в группе.", show_alert=True)
        return
    try:
        page = int((query.data or "").rsplit(":", 1)[1])
    except (IndexError, ValueError):
        await query.answer("Некорректная страница.", show_alert=True)
        return
    text, markup = await queue_view(query.message.chat.id, page)
    try:
        await query.bot.edit_message_text(
            chat_id=query.message.chat.id,
            message_id=query.message.message_id,
            text=text,
            reply_markup=markup,
        )
    except TelegramBadRequest as error:
        if "message is not modified" not in str(error).lower():
            raise
    await query.answer()


@router.message(Command("queue_next"))
async def next_in_queue(message: Message) -> None:
    if not is_group(message):
        await message.answer("Команда работает только в группе.")
        return
    person = await user_service.next_queued_user(message.chat.id, sender(message))
    if person is None:
        await message.answer("Пока нет других участников для очереди.")
        return
    name = escape(person.first_name)
    await message.answer(
        f'Следующий в очереди: <a href="tg://user?id={person.user_id}">{name}</a>'
    )


async def change_participation(
    message: Message, excluded: bool, queue: bool = False
) -> None:
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
            if queue:
                selected = await user_service.set_queue_participation_by_username(
                    message.chat.id, actor, username, excluded
                )
            else:
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
        if queue:
            changed = await user_service.set_queue_participation(
                message.chat.id, actor, target, excluded
            )
        else:
            changed = await user_service.set_participation(
                message.chat.id, actor, target, excluded
            )
        if not changed:
            await message.answer("Участник не найден в списке.")
            return
        name = target.first_name
    if queue:
        action = "исключён из очереди" if excluded else "снова участвует в очереди"
    else:
        action = "исключён из выбора" if excluded else "снова участвует в выборе"
    await message.answer(f"{escape(name)} {action}.")


@router.message(Command("exclude"))
async def exclude(message: Message) -> None:
    await change_participation(message, True)


@router.message(Command("include"))
async def include(message: Message) -> None:
    await change_participation(message, False)


@router.message(Command("queue_exclude"))
async def queue_exclude(message: Message) -> None:
    await change_participation(message, True, queue=True)


@router.message(Command("queue_include"))
async def queue_include(message: Message) -> None:
    await change_participation(message, False, queue=True)
