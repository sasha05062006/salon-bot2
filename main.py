import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, BotCommandScopeChat
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN
from database import init_db, seed_catalog
from handlers import start, booking, admin


async def main():
    logging.basicConfig(level=logging.INFO)

    await init_db()
    await seed_catalog()

    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())

    dp.include_router(start.router)
    dp.include_router(booking.router)
    dp.include_router(admin.router)

    # Admin-only command menu in Telegram.
    from config import ADMIN_ID
    await bot.set_my_commands(
        [
            BotCommand(command="bookings", description="Открыть панель записей"),
            BotCommand(command="salon_setup", description="Настройки салона"),
            BotCommand(command="bot_settings", description="Настройки бота"),
        ],
        scope=BotCommandScopeChat(chat_id=ADMIN_ID),
    )

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
