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


async def reminder_loop(bot):
    from database import get_confirmed_bookings_for_reminders, mark_reminder
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Asia/Tashkent")
    while True:
        try:
            now = datetime.now(tz)
            for b in await get_confirmed_bookings_for_reminders():
                try:
                    dt = datetime.strptime(f"{now.year}.{b['date']}.{b['time']}", "%Y.%d.%m.%H:%M").replace(tzinfo=tz)
                    delta = dt - now
                    if timedelta(hours=23, minutes=30) <= delta <= timedelta(hours=24, minutes=30) and not b.get("reminder_24_sent"):
                        await bot.send_message(b["user_id"], f"⏰ <b>Напоминание о записи</b>\n\n💇 {b['service']}\n👩‍🎨 {b['master']}\n📅 {b['date']} · {b['time']}\n\nЖдём вас!")
                        await mark_reminder(b["id"], "24h")
                    if timedelta(minutes=90) <= delta <= timedelta(hours=2, minutes=30) and not b.get("reminder_2_sent"):
                        await bot.send_message(b["user_id"], f"🔔 <b>Напоминание: запись уже скоро</b>\n\n💇 {b['service']}\n👩‍🎨 {b['master']}\n📅 {b['date']} · {b['time']}")
                        await mark_reminder(b["id"], "2h")
                except Exception:
                    logging.exception("Reminder processing failed for booking %s", b.get("id"))
        except Exception:
            logging.exception("Reminder loop failed")
        await asyncio.sleep(60)


async def main():
    logging.basicConfig(level=logging.INFO)
    bot = None
    try:
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

        asyncio.create_task(reminder_loop(bot))

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
    except Exception:
        logging.exception("Application startup/runtime failure")
        if bot:
            try:
                await bot.session.close()
            except Exception:
                pass
        try:
            await start_webapp()
        except Exception:
            logging.exception("Failed to start fallback web server")
            raise
        while True:
            await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())
