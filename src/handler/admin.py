import re
from html import escape

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from handler.common import GROUP_TYPES, is_group, remember_sender, sender
from service.membership import is_active_member
from service.users import user_service


router = Router(name="admin")
PAGE_SIZE = 10


class AdminState(StatesGroup):
    adding = State()
    updating = State()
    deleting = State()


def admin_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Список", callback_data="admin:list:0")],
        [
            InlineKeyboardButton(text="Добавить", callback_data="admin:add"),
            InlineKeyboardButton(text="Обновить", callback_data="admin:update"),
        ],
        [InlineKeyboardButton(text="Удалить", callback_data="admin:delete")],
    ])


def parse_user_details(text: str | None) -> tuple[int, str, str | None] | None:
    if not text:
        return None
    parts = [part.strip() for part in text.split("|")]
    if len(parts) != 3 or not parts[0].isdigit():
        return None
    user_id = int(parts[0])
    name = parts[1]
    username = parts[2].lstrip("@") if parts[2] != "-" else None
    if user_id <= 0 or not name or len(name) > 255:
        return None
    if username is not None and not re.fullmatch(r"[A-Za-z0-9_]{1,255}", username):
        return None
    return user_id, name, username


@router.message(Command("admin"))
async def admin_panel(message: Message, state: FSMContext) -> None:
    if not is_group(message):
        await message.answer("Админка доступна только в группе.")
        return
    if sender(message) is None:
        await message.answer("Не удалось определить пользователя.")
        return
    await state.clear()
    await remember_sender(message)
    await message.answer("Управление участниками этой группы:", reply_markup=admin_keyboard())


@router.message(Command("cancel"))
async def cancel_admin_action(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Действие отменено.")


@router.callback_query(F.data.startswith("admin:"))
async def admin_callback(query: CallbackQuery, state: FSMContext) -> None:
    if query.message is None or query.message.chat.type not in GROUP_TYPES:
        await query.answer("Админка доступна только в группе.", show_alert=True)
        return
    chat_id = query.message.chat.id
    if query.from_user.is_bot:
        await query.answer("Недоступно для ботов.", show_alert=True)
        return
    action = (query.data or "").split(":")
    if len(action) < 2:
        await query.answer("Неизвестное действие.", show_alert=True)
        return
    if action[1] == "menu":
        await state.clear()
        await query.bot.send_message(chat_id, "Управление участниками:", reply_markup=admin_keyboard())
    elif action[1] == "list":
        try:
            page = max(0, int(action[2]))
        except (IndexError, ValueError):
            await query.answer("Некорректная страница.", show_alert=True)
            return
        count, page, users = await user_service.list_page(chat_id, page, PAGE_SIZE)
        lines = [f"Участники в базе: {count}. Страница {page + 1}.\n"]
        for user in users:
            status = "вышел" if not user.is_active else "исключён" if user.is_excluded else "участвует"
            username = f" @{escape(user.username[:32])}" if user.username else ""
            lines.append(f"{user.user_id} — {escape(user.first_name[:80])}{username} ({status})")
        if not users:
            lines.append("Список пуст.")
        navigation = []
        if page > 0:
            navigation.append(InlineKeyboardButton(text="←", callback_data=f"admin:list:{page - 1}"))
        if (page + 1) * PAGE_SIZE < count:
            navigation.append(InlineKeyboardButton(text="→", callback_data=f"admin:list:{page + 1}"))
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            *([navigation] if navigation else []),
            [InlineKeyboardButton(text="Меню", callback_data="admin:menu")],
        ])
        await query.bot.send_message(chat_id, "\n".join(lines), reply_markup=keyboard)
    elif action[1] in {"add", "update", "delete"}:
        await state.clear()
        if action[1] == "add":
            await state.set_state(AdminState.adding)
            prompt = "Пришлите: ID | Имя | @username. Если username нет, поставьте -. Для отмены: /cancel"
        elif action[1] == "update":
            await state.set_state(AdminState.updating)
            prompt = "Пришлите: ID | Новое имя | @username. Для удаления username поставьте -. Для отмены: /cancel"
        else:
            await state.set_state(AdminState.deleting)
            prompt = "Пришлите ID пользователя для удаления. Для отмены: /cancel"
        await query.bot.send_message(chat_id, prompt)
    elif action[1] == "confirm" and len(action) == 4:
        try:
            user_id, requester_id = int(action[2]), int(action[3])
        except ValueError:
            await query.answer("Некорректное действие.", show_alert=True)
            return
        if requester_id != query.from_user.id:
            await query.answer("Подтвердить может только инициатор удаления.", show_alert=True)
            return
        if (await state.get_data()).get("pending_delete") != user_id:
            await query.answer("Это подтверждение уже недействительно.", show_alert=True)
            return
        await state.clear()
        deleted = await user_service.delete_user(chat_id, user_id)
        await query.bot.send_message(
            chat_id,
            "Запись удалена." if deleted else "Запись уже отсутствует.",
            reply_markup=admin_keyboard(),
        )
    else:
        await query.answer("Неизвестное действие.", show_alert=True)
        return
    await query.answer()


@router.message(StateFilter(AdminState.adding, AdminState.updating, AdminState.deleting))
async def admin_input(message: Message, state: FSMContext) -> None:
    if not is_group(message) or sender(message) is None:
        return
    current_state = await state.get_state()
    if current_state == AdminState.deleting.state:
        if not message.text or not message.text.strip().isdigit() or int(message.text.strip()) <= 0:
            await message.answer("Пришлите числовой ID пользователя.")
            return
        user_id = int(message.text.strip())
        user = await user_service.get_user(message.chat.id, user_id)
        if user is None:
            await message.answer("Запись не найдена. Пришлите другой ID или /cancel.")
            return
        await state.clear()
        await state.update_data(pending_delete=user_id)
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="Да, удалить",
                callback_data=f"admin:confirm:{user_id}:{message.from_user.id}",
            )],
            [InlineKeyboardButton(text="Отмена", callback_data="admin:menu")],
        ])
        await message.answer(
            f"Удалить запись {escape(user.first_name)} (ID {user_id})?",
            reply_markup=keyboard,
        )
        return
    details = parse_user_details(message.text)
    if details is None:
        await message.answer("Нужен формат: ID | Имя | @username (или - вместо username).")
        return
    user_id, name, username = details
    if current_state == AdminState.adding.state:
        try:
            member = await message.bot.get_chat_member(message.chat.id, user_id)
        except TelegramAPIError:
            await message.answer("Не удалось проверить участника. Проверьте ID и права бота.")
            return
        if not is_active_member(member) or member.user.is_bot:
            await message.answer("Добавить можно только человека, который состоит в группе.")
            return
        changed = await user_service.add_user(message.chat.id, user_id, name, username)
        response = "Пользователь добавлен." if changed else "Запись уже есть. Используйте «Обновить»."
    else:
        changed = await user_service.update_user(message.chat.id, user_id, name, username)
        response = "Запись обновлена." if changed else "Запись не найдена. Используйте «Добавить»."
    await state.clear()
    await message.answer(response, reply_markup=admin_keyboard())
