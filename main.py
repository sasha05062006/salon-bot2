import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, BotCommandScopeChat, MenuButtonWebApp, WebAppInfo
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import BOT_TOKEN, ADMIN_ID, WEBAPP_URL
from database import init_db, seed_catalog
from handlers import start, booking, admin
from webapp import start_webapp


async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db()
    await seed_catalog()

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(start.router)
    dp.include_router(booking.router)
    dp.include_router(admin.router)

    await bot.set_my_commands(
        [
            BotCommand(command="bookings", description="Открыть панель записей"),
            BotCommand(command="salon_setup", description="Настройки салона"),
            BotCommand(command="bot_settings", description="Настройки бота"),
        ],
        scope=BotCommandScopeChat(chat_id=ADMIN_ID),
    )

    # Mini App is a normal Telegram menu button for every user.
    # Access to the admin records inside the app is still protected by ADMIN_ID.
    if WEBAPP_URL:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="📱 Приложение",
                web_app=WebAppInfo(url=WEBAPP_URL),
            )
        )
        await bot.set_chat_menu_button(
            chat_id=ADMIN_ID,
            menu_button=MenuButtonWebApp(
                text="📱 Приложение",
                web_app=WebAppInfo(url=WEBAPP_URL),
            )
        )
        logging.info("Telegram Mini App URL: %s", WEBAPP_URL)
    else:
        logging.warning("WEBAPP_URL is empty. Generate a public Railway domain or set WEBAPP_URL.")

    await start_webapp()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
