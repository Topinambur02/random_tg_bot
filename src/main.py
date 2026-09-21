import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from db.session import db_manager
from handler.admin import router as admin_router
from handler.commands import router as commands_router
from handler.events import router as events_router
from settings import settings


dp = Dispatcher()
dp.include_routers(commands_router, admin_router, events_router)


async def main() -> None:
    await db_manager.create_tables()
    bot = Bot(
        token=settings.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        await dp.start_polling(bot, allowed_updates=["message", "chat_member", "callback_query"])
    finally:
        await db_manager.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
