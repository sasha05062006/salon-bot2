import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl

from aiohttp import web

from config import ADMIN_ID, BOT_TOKEN, WEBAPP_URL
from database import add_booking, get_all_bookings, get_booking, get_master, get_masters_for_service, get_service, get_services, get_salon_settings, is_slot_available, update_booking_status, get_master_schedule, get_bookings_for_user

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "webapp"


def _validate_init_data(init_data: str) -> dict:
    if not init_data:
        raise web.HTTPUnauthorized(text="Telegram authorization required")
    bot_token = os.getenv("BOT_TOKEN", "")
    if not bot_token:
        raise web.HTTPInternalServerError(text="BOT_TOKEN is not configured")

    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise web.HTTPUnauthorized(text="Invalid Telegram initData")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated_hash, received_hash):
        raise web.HTTPUnauthorized(text="Invalid Telegram signature")

    auth_date = int(pairs.get("auth_date", "0") or 0)
    if not auth_date or datetime.now().timestamp() - auth_date > 86400:
        raise web.HTTPUnauthorized(text="Telegram session expired")

    user = json.loads(pairs.get("user", "{}"))
    if not user.get("id"):
        raise web.HTTPUnauthorized(text="Telegram user not found")
    return user


def _user_from_request(request: web.Request) -> dict:
    return _validate_init_data(request.headers.get("X-Telegram-Init-Data", ""))


def _is_admin(user: dict) -> bool:
    return int(user.get("id", 0)) == int(ADMIN_ID)


async def health(request):
    return web.json_response({"ok": True})


async def me(request):
    user = _user_from_request(request)
    return web.json_response({
        "ok": True,
        "user": {
            "id": user["id"],
            "first_name": user.get("first_name", ""),
            "last_name": user.get("last_name", ""),
            "username": user.get("username", ""),
        },
        "is_admin": _is_admin(user),
        "salon": await get_salon_settings(),
    })


async def catalog(request):
    user = _user_from_request(request)
    lang = request.query.get("lang", "ru")
    services = await get_services()
    result = []
    for service in services:
        masters = await get_masters_for_service(service["key"])
        result.append({
            "key": service["key"],
            "name": service["name_ru"] if lang == "ru" else service["name_uz"],
            "price": service["price"],
            "duration": service["duration"],
            "masters": [
                {"key": m["key"], "name": m["name_ru"] if lang == "ru" else m["name_uz"], "schedule": [{"weekday": int(r[0]), "start": r[1], "end": r[2], "lunch_start": r[3], "lunch_end": r[4]} for r in await get_master_schedule(m["key"])]}
                for m in masters
            ],
        })
    return web.json_response({"ok": True, "services": result, "salon": await get_salon_settings(), "is_admin": _is_admin(user)})


async def _notify_admin(booking):
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        text = (
            "🔔 <b>Новая запись!</b>\n\n"
            f"🆔 Запись №{booking['id']}\n"
            f"💇 <b>{booking['service']}</b>\n"
            f"👩‍🎨 Мастер: {booking['master']}\n"
            f"📅 {booking['date']} · {booking['time']}\n"
            f"👤 Клиент: {booking['name']}\n"
            f"📞 Телефон: {booking['phone']}"
            + (f"\n💬 Telegram: @{booking['username']}" if booking.get('username') else "")
        )
        await bot.send_message(
            ADMIN_ID, text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 Открыть записи", url=WEBAPP_URL)]
            ])
        )
    finally:
        await bot.session.close()


async def _notify_client(booking):
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        lang = booking.get("lang", "ru")
        if booking["status"] == "confirmed":
            text = (
                "✅ <b>Ваша запись подтверждена!</b>\n\n"
                f"💇 {booking['service']}\n"
                f"👩‍🎨 {booking['master']}\n"
                f"📅 {booking['date']} · {booking['time']}\n\n"
                "Ждём вас! До встречи 💫"
            ) if lang == "ru" else (
                "✅ <b>Yozuvingiz tasdiqlandi!</b>\n\n"
                f"💇 {booking['service']}\n"
                f"👩‍🎨 {booking['master']}\n"
                f"📅 {booking['date']} · {booking['time']}\n\n"
                "Sizni kutamiz! Ko‘rishguncha 💫"
            )
        else:
            text = (
                "❌ <b>Ваша запись отменена.</b>\n\n"
                f"{booking['service']} · {booking['date']} · {booking['time']}"
            ) if lang == "ru" else (
                "❌ <b>Yozuvingiz bekor qilindi.</b>\n\n"
                f"{booking['service']} · {booking['date']} · {booking['time']}"
            )
        await bot.send_message(booking["user_id"], text)
    finally:
        await bot.session.close()


async def create_web_booking(request):
    user = _user_from_request(request)
    try:
        data = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="Invalid JSON")

    required = ["service_key", "master_key", "date", "time", "name", "phone"]
    missing = [key for key in required if not str(data.get(key, "")).strip()]
    if missing:
        raise web.HTTPBadRequest(text="Missing: " + ", ".join(missing))

    service = await get_service(data["service_key"])
    master = await get_master(data["master_key"])
    if not service or not master:
        raise web.HTTPBadRequest(text="Service or master is unavailable")

    allowed = await get_masters_for_service(service["key"])
    if master["key"] not in {m["key"] for m in allowed}:
        raise web.HTTPForbidden(text="This master is not assigned to the service")

    date, time = str(data["date"]), str(data["time"])
    try:
        parsed_input_date = datetime.strptime(date, "%d.%m")
        datetime.strptime(time, "%H:%M")
    except ValueError:
        raise web.HTTPBadRequest(text="Invalid date or time")

    now_tz = datetime.now(__import__("zoneinfo").ZoneInfo("Asia/Tashkent"))
    booking_year = now_tz.year
    if parsed_input_date.month < now_tz.month and (now_tz.month - parsed_input_date.month) >= 6:
        booking_year += 1
    booking_date = parsed_input_date.replace(year=booking_year)
    if booking_date.date() < now_tz.date():
        raise web.HTTPConflict(text="Cannot book a past date")

    duration = int(service["duration"])

    # Final server-side working-hours check.
    parsed_date = datetime.strptime(date, "%d.%m")
    now_tz = datetime.now(__import__("zoneinfo").ZoneInfo("Asia/Tashkent"))
    year = now_tz.year
    if parsed_date.month < now_tz.month and (now_tz.month - parsed_date.month) >= 6:
        year += 1
    weekday = parsed_date.replace(year=year).weekday()
    schedule_rows = await get_master_schedule(master["key"])
    day_ranges = [(r[1], r[2], r[3], r[4]) for r in schedule_rows if int(r[0]) == weekday]
    start_dt = datetime.strptime(time, "%H:%M")
    end_dt = start_dt + __import__("datetime").timedelta(minutes=duration)
    if not any(
        start_dt >= datetime.strptime(start, "%H:%M") and end_dt <= datetime.strptime(end, "%H:%M")
        and not (lunch_start and lunch_end and start_dt < datetime.strptime(lunch_end, "%H:%M") and end_dt > datetime.strptime(lunch_start, "%H:%M"))
        for start, end, lunch_start, lunch_end in day_ranges
    ):
        raise web.HTTPConflict(text="This time is outside the master's working hours or overlaps lunch break")

    if not await is_slot_available(date, time, duration, master["name_ru"]):
        raise web.HTTPConflict(text="This time is already booked")

    saved = await add_booking(
        user_id=int(user["id"]),
        username=user.get("username", ""),
        service=service["name_ru"],
        master=master["name_ru"],
        date=date,
        time=time,
        name=str(data["name"]).strip(),
        phone=str(data["phone"]).strip(),
        lang=str(data.get("lang", "ru")),
        duration=duration,
    )
    if not saved:
        raise web.HTTPConflict(text="This time is already booked")
    booking = await get_booking(saved)
    if booking:
        try:
            await _notify_admin(booking)
        except Exception:
            logging.exception("Failed to notify admin about booking %s", booking.get("id"))
    return web.json_response({"ok": True})


async def my_bookings(request):
    user = _user_from_request(request)
    return web.json_response({"ok": True, "bookings": await get_bookings_for_user(int(user["id"]))})


async def bookings(request):
    user = _user_from_request(request)
    if not _is_admin(user):
        raise web.HTTPForbidden(text="Admin access required")
    return web.json_response({"ok": True, "bookings": await get_all_bookings()})


async def booking_detail(request):
    user = _user_from_request(request)
    if not _is_admin(user):
        raise web.HTTPForbidden(text="Admin access required")
    booking = await get_booking(int(request.match_info["booking_id"]))
    if not booking:
        raise web.HTTPNotFound(text="Booking not found")
    return web.json_response({"ok": True, "booking": booking})


async def booking_status(request):
    user = _user_from_request(request)
    if not _is_admin(user):
        raise web.HTTPForbidden(text="Admin access required")
    booking_id = int(request.match_info["booking_id"])
    try:
        data = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="Invalid JSON")
    status = str(data.get("status", ""))
    if status not in {"new", "confirmed", "cancelled"}:
        raise web.HTTPBadRequest(text="Invalid status")
    if not await update_booking_status(booking_id, status):
        raise web.HTTPNotFound(text="Booking not found")
    updated = await get_booking(booking_id)
    if updated:
        try:
            await _notify_client(updated)
        except Exception:
            logging.exception("Failed to notify client %s about booking %s", updated.get("user_id"), booking_id)
    return web.json_response({"ok": True, "booking": updated})


async def index(request):
    return web.FileResponse(STATIC_DIR / "index.html")


def create_app():
    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_get("/api/me", me)
    app.router.add_get("/api/catalog", catalog)
    app.router.add_post("/api/bookings", create_web_booking)
    app.router.add_get("/api/my-bookings", my_bookings)
    app.router.add_get("/api/admin/bookings", bookings)
    app.router.add_get("/api/admin/bookings/{booking_id}", booking_detail)
    app.router.add_patch("/api/admin/bookings/{booking_id}/status", booking_status)
    app.router.add_get("/", index)
    app.router.add_static("/", STATIC_DIR, show_index=False)
    return app


async def start_webapp():
    runner = web.AppRunner(create_app())
    await runner.setup()
    await web.TCPSite(runner, os.getenv("WEBAPP_HOST", "0.0.0.0"), int(os.getenv("PORT") or os.getenv("WEBAPP_PORT", "8080"))).start()
    return runner
