from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from handler.common import GROUP_TYPES, is_group, remember_sender, sender
from repository.user_repository import AmbiguousUsernameError, UsernameInUseError
from service.membership import is_active_member
from service.usernames import parse_username
from service.users import user_service


router = Router(name="admin")
PAGE_SIZE = 8
MENU_TEXT = "Управление участниками этой группы. Выберите действие:"
ADD_PROMPT = (
    "Пришлите @username участника. Если бот его ещё не знает, ответьте "
    "на его сообщение строкой @username. Для отмены нажмите «Назад»."
)


class PanelState(StatesGroup):
    adding = State()
    updating = State()


def button(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)


def menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [button("Участники", "admin:list:0")],
        [button("Добавить участника", "admin:add")],
    ])


def back_keyboard(data: str = "admin:menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[button("← Назад", data)]])


def user_label(first_name: str, username: str | None) -> str:
    handle = f"@{username}" if username else "без @username"
    return f"{first_name[:25]} · {handle[:33]}"


async def list_view(chat_id: int, page: int) -> tuple[str, InlineKeyboardMarkup]:
    count, page, users = await user_service.list_page(chat_id, page, PAGE_SIZE)
    lines = [f"Участники в базе: {count}. Страница {page + 1}."]
    rows = []
    for user in users:
        status = "вышел" if not user.is_active else "исключён" if user.is_excluded else "участвует"
        handle = f"@{escape(user.username)}" if user.username else "без @username"
        lines.append(f"{handle} — {escape(user.first_name[:60])} ({status})")
        rows.append([button(user_label(user.first_name, user.username), f"admin:user:{user.user_id}:{page}")])
    if not users:
        lines.append("Список пуст.")
    navigation = []
    if page > 0:
        navigation.append(button("←", f"admin:list:{page - 1}"))
    if (page + 1) * PAGE_SIZE < count:
        navigation.append(button("→", f"admin:list:{page + 1}"))
    if navigation:
        rows.append(navigation)
    rows.append([button("Меню", "admin:menu")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=rows)


async def user_view(
    chat_id: int, user_id: int, page: int
) -> tuple[str, InlineKeyboardMarkup]:
    user = await user_service.get_user(chat_id, user_id)
    if user is None:
        return await list_view(chat_id, page)
    status = "вышел из группы" if not user.is_active else "исключён из выбора" if user.is_excluded else "участвует в выборе"
    handle = f"@{escape(user.username)}" if user.username else "нет @username"
    text = f"Участник: {escape(user.first_name)}\nUsername: {handle}\nСтатус: {status}"
    rows = []
    if user.is_active:
        action = "Вернуть в выбор" if user.is_excluded else "Исключить из выбора"
        flag = 0 if user.is_excluded else 1
        rows.append([button(action, f"admin:toggle:{user_id}:{page}:{flag}")])
    rows.extend([
        [button("Изменить", f"admin:update:{user_id}:{page}")],
        [button("Удалить", f"admin:delete:{user_id}:{page}")],
        [button("← К списку", f"admin:list:{page}")],
    ])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


async def reset_panel(state: FSMContext, message_id: int) -> None:
    await state.clear()
    await state.update_data(panel_message_id=message_id)


async def edit_callback_panel(
    query: CallbackQuery, text: str, markup: InlineKeyboardMarkup
) -> None:
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


async def edit_input_panel(
    message: Message, state: FSMContext, panel_id: int, text: str,
    markup: InlineKeyboardMarkup,
) -> None:
    try:
        await message.bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=panel_id,
            text=text,
            reply_markup=markup,
        )
    except TelegramBadRequest as error:
        if "message is not modified" in str(error).lower():
            return
        panel = await message.answer(text, reply_markup=markup)
        await state.update_data(panel_message_id=panel.message_id)


@router.message(Command("admin"))
async def admin_panel(message: Message, state: FSMContext) -> None:
    if not is_group(message):
        await message.answer("Панель доступна только в группе.")
        return
    if sender(message) is None:
        await message.answer("Не удалось определить пользователя.")
        return
    await remember_sender(message)
    panel_id = (await state.get_data()).get("panel_message_id")
    if panel_id is not None:
        try:
            await message.bot.edit_message_text(
                chat_id=message.chat.id,
                message_id=panel_id,
                text=MENU_TEXT,
                reply_markup=menu_keyboard(),
            )
        except TelegramBadRequest as error:
            if "message is not modified" not in str(error).lower():
                panel_id = None
    if panel_id is None:
        panel = await message.answer(MENU_TEXT, reply_markup=menu_keyboard())
        panel_id = panel.message_id
    await reset_panel(state, panel_id)


@router.message(Command("cancel"))
async def cancel_panel_action(message: Message, state: FSMContext) -> None:
    panel_id = (await state.get_data()).get("panel_message_id")
    if panel_id is None or not is_group(message):
        return
    await reset_panel(state, panel_id)
    await edit_input_panel(message, state, panel_id, MENU_TEXT, menu_keyboard())


@router.callback_query(F.data.startswith("admin:"))
async def admin_callback(query: CallbackQuery, state: FSMContext) -> None:
    if query.message is None or query.message.chat.type not in GROUP_TYPES:
        await query.answer("Панель доступна только в группе.", show_alert=True)
        return
    if query.from_user.is_bot:
        await query.answer("Недоступно для ботов.", show_alert=True)
        return
    panel_id = query.message.message_id
    if (await state.get_data()).get("panel_message_id") != panel_id:
        await query.answer("Откройте свою панель командой /admin.", show_alert=True)
        return
    chat_id = query.message.chat.id
    action = (query.data or "").split(":")
    try:
        if action[1] == "menu" and len(action) == 2:
            await reset_panel(state, panel_id)
            text, markup = MENU_TEXT, menu_keyboard()
        elif action[1] == "list" and len(action) == 3:
            page = max(0, int(action[2]))
            await reset_panel(state, panel_id)
            text, markup = await list_view(chat_id, page)
        elif action[1] == "user" and len(action) == 4:
            user_id, page = int(action[2]), max(0, int(action[3]))
            await reset_panel(state, panel_id)
            text, markup = await user_view(chat_id, user_id, page)
        elif action[1] == "add" and len(action) == 2:
            await reset_panel(state, panel_id)
            await state.set_state(PanelState.adding)
            text, markup = ADD_PROMPT, back_keyboard()
        elif action[1] == "update" and len(action) == 4:
            user_id, page = int(action[2]), max(0, int(action[3]))
            user = await user_service.get_user(chat_id, user_id)
            if user is None:
                text, markup = await list_view(chat_id, page)
            else:
                await reset_panel(state, panel_id)
                await state.set_state(PanelState.updating)
                await state.update_data(selected_user_id=user_id, page=page)
                text = (
                    f"Изменить {escape(user.first_name)}. Пришлите новое имя или "
                    "«Новое имя | @новый_username»."
                )
                markup = back_keyboard(f"admin:user:{user_id}:{page}")
        elif action[1] == "delete" and len(action) == 4:
            user_id, page = int(action[2]), max(0, int(action[3]))
            user = await user_service.get_user(chat_id, user_id)
            if user is None:
                text, markup = await list_view(chat_id, page)
            else:
                await reset_panel(state, panel_id)
                await state.update_data(pending_delete=user_id)
                text = f"Удалить запись {escape(user.first_name)}?"
                markup = InlineKeyboardMarkup(inline_keyboard=[
                    [button("Да, удалить", f"admin:confirm:{user_id}:{page}")],
                    [button("Отмена", f"admin:user:{user_id}:{page}")],
                ])
        elif action[1] == "toggle" and len(action) == 5:
            user_id, page, flag = int(action[2]), max(0, int(action[3])), int(action[4])
            if flag not in {0, 1}:
                raise ValueError
            user = await user_service.set_participation_for_user(chat_id, user_id, bool(flag))
            await reset_panel(state, panel_id)
            text, markup = await user_view(chat_id, user_id, page)
            if user is None:
                text = "Участник неактивен или удалён.\n\n" + text
        elif action[1] == "confirm" and len(action) == 4:
            user_id, page = int(action[2]), max(0, int(action[3]))
            if (await state.get_data()).get("pending_delete") != user_id:
                await query.answer("Подтверждение уже недействительно.", show_alert=True)
                return
            deleted = await user_service.delete_user(chat_id, user_id)
            await reset_panel(state, panel_id)
            text, markup = await list_view(chat_id, page)
            text = ("Запись удалена.\n\n" if deleted else "Запись уже отсутствует.\n\n") + text
        else:
            raise ValueError
    except (ValueError, IndexError):
        await query.answer("Неизвестное действие.", show_alert=True)
        return
    await edit_callback_panel(query, text, markup)
    await query.answer()


@router.message(StateFilter(PanelState.adding, PanelState.updating))
async def admin_input(message: Message, state: FSMContext) -> None:
    actor = sender(message)
    if not is_group(message) or actor is None:
        return
    data = await state.get_data()
    panel_id = data.get("panel_message_id")
    if panel_id is None:
        await state.clear()
        return
    current_state = await state.get_state()
    if current_state == PanelState.adding.state:
        username = parse_username(message.text)
        if username is None:
            await edit_input_panel(message, state, panel_id, "Нужен Telegram @username.\n\n" + ADD_PROMPT, back_keyboard())
            return
        try:
            user = await user_service.get_user_by_username(message.chat.id, username)
        except AmbiguousUsernameError:
            await edit_input_panel(message, state, panel_id, "В базе несколько записей с этим @username.", back_keyboard())
            return
        if user is not None and user.is_active:
            await reset_panel(state, panel_id)
            await edit_input_panel(message, state, panel_id, "Участник уже есть в списке.\n\n" + MENU_TEXT, menu_keyboard())
            return
        target = None
        if user is None and message.reply_to_message is not None:
            target = sender(message.reply_to_message)
            if target is None or target.username is None or target.username.lower() != username.lower():
                await edit_input_panel(message, state, panel_id, "Ответьте на сообщение человека с указанным @username.\n\n" + ADD_PROMPT, back_keyboard())
                return
        if user is None and target is None:
            await edit_input_panel(message, state, panel_id, "Бот ещё не знает этого @username. Ответьте на сообщение человека или попросите его написать в группе.\n\n" + ADD_PROMPT, back_keyboard())
            return
        target_id = user.user_id if user is not None else target.id
        try:
            member = await message.bot.get_chat_member(message.chat.id, target_id)
        except TelegramAPIError:
            await edit_input_panel(message, state, panel_id, "Не удалось проверить участника. Проверьте права бота.\n\n" + ADD_PROMPT, back_keyboard())
            return
        member_username = member.user.username
        if (
            not is_active_member(member)
            or member.user.is_bot
            or member_username is None
            or member_username.lower() != username.lower()
        ):
            await edit_input_panel(message, state, panel_id, "Участник не состоит в группе или его @username изменился.\n\n" + ADD_PROMPT, back_keyboard())
            return
        try:
            changed = await user_service.add_user(
                message.chat.id, target_id, member.user.first_name, member_username
            )
        except (AmbiguousUsernameError, UsernameInUseError):
            await edit_input_panel(message, state, panel_id, "Этот @username уже связан с другой записью.\n\n" + ADD_PROMPT, back_keyboard())
            return
        await reset_panel(state, panel_id)
        result = "Пользователь добавлен." if changed else "Участник уже есть в списке."
        await edit_input_panel(message, state, panel_id, result + "\n\n" + MENU_TEXT, menu_keyboard())
        return

    user_id = data.get("selected_user_id")
    page = data.get("page", 0)
    if user_id is None:
        await reset_panel(state, panel_id)
        await edit_input_panel(message, state, panel_id, MENU_TEXT, menu_keyboard())
        return
    user = await user_service.get_user(message.chat.id, user_id)
    if user is None:
        await reset_panel(state, panel_id)
        text, markup = await list_view(message.chat.id, page)
        await edit_input_panel(message, state, panel_id, "Запись уже удалена.\n\n" + text, markup)
        return
    parts = [part.strip() for part in (message.text or "").split("|")]
    name = parts[0]
    username = user.username
    if len(parts) == 2:
        username = parse_username(parts[1])
    if len(parts) not in {1, 2} or not name or len(name) > 255 or (len(parts) == 2 and username is None):
        await edit_input_panel(
            message, state, panel_id,
            "Нужен формат: Новое имя [| @новый_username].",
            back_keyboard(f"admin:user:{user_id}:{page}"),
        )
        return
    try:
        updated = await user_service.update_user(message.chat.id, user_id, name, username)
    except (AmbiguousUsernameError, UsernameInUseError):
        await edit_input_panel(message, state, panel_id, "Этот @username уже связан с другой записью.", back_keyboard(f"admin:user:{user_id}:{page}"))
        return
    await reset_panel(state, panel_id)
    if updated:
        text, markup = await user_view(message.chat.id, user_id, page)
        text = "Запись обновлена.\n\n" + text
    else:
        text, markup = await list_view(message.chat.id, page)
        text = "Запись уже удалена.\n\n" + text
    await edit_input_panel(message, state, panel_id, text, markup)
