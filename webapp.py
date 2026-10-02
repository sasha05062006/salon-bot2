import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.parse import parse_qsl

from aiohttp import web

from config import ADMIN_ID, BOT_TOKEN, WEBAPP_URL
from database import add_booking, get_all_bookings, get_booking, get_master, get_masters_for_service, get_service, get_services, get_salon_settings, is_slot_available, update_booking_status, get_master_schedule, get_bookings_for_user, update_booking_details, get_bookings_filtered, get_booking_stats, update_booking_status, get_admin_catalog, add_master, set_master_telegram_id, get_master_by_telegram_id, get_bookings_for_master, get_master_by_name, deactivate_master, add_service, deactivate_service, update_service, set_master_service, set_master_day

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


async def maintenance(request):
    return web.Response(
        text="""<!doctype html><html lang="ru"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Технические работы</title><style>body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0f1115;color:#fff;font-family:system-ui,-apple-system,sans-serif;padding:24px;box-sizing:border-box}.box{text-align:center;max-width:420px;padding:32px;border:1px solid #292d36;border-radius:24px;background:#171a21}h1{font-size:24px;margin:0 0 12px}p{color:#aeb4c0;line-height:1.5;margin:8px 0} .icon{font-size:48px;margin-bottom:12px}</style></head><body><main class="box"><div class="icon">🛠️</div><h1>Ведутся технические работы</h1><p>Приложение временно недоступно.</p><p>Мы уже занимаемся восстановлением работы. Пожалуйста, попробуйте зайти немного позже.</p></main></body></html>""",
        content_type="text/html",
        status=503,
    )

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
        "is_master": bool(await get_master_by_telegram_id(int(user["id"]))),
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
    return web.json_response({"ok": True, "services": result, "masters": await __import__("database").get_masters(), "salon": await get_salon_settings(), "is_admin": _is_admin(user)})


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


async def _notify_client(booking, event=None):
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        lang = booking.get("lang", "ru")
        if event == "rescheduled":
            text = (
                "🔄 <b>Ваша запись перенесена.</b>\n\n"
                f"💇 {booking['service']}\n"
                f"👩‍🎨 {booking['master']}\n"
                f"📅 {booking['date']} · {booking['time']}\n\n"
                "Пожалуйста, сохраните новое время."
            ) if lang == "ru" else (
                "🔄 <b>Yozuvingiz boshqa vaqtga ko‘chirildi.</b>\n\n"
                f"💇 {booking['service']}\n"
                f"👩‍🎨 {booking['master']}\n"
                f"📅 {booking['date']} · {booking['time']}\n\n"
                "Yangi vaqtni saqlab qo‘ying."
            )
        elif booking["status"] == "confirmed":
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
            master_row = await get_master_by_name(booking["master"])
            if master_row and master_row.get("telegram_id"):
                from aiogram import Bot
                bot = Bot(BOT_TOKEN)
                try:
                    await bot.send_message(master_row["telegram_id"], f"📋 <b>Новая запись к вам</b>\n\n💇 {booking['service']}\n👤 {booking['name']}\n📞 {booking['phone']}\n📅 {booking['date']} · {booking['time']}")
                finally:
                    await bot.session.close()
        except Exception:
            logging.exception("Failed to notify master about web booking")
        try:
            await _notify_admin(booking)
        except Exception:
            logging.exception("Failed to notify admin about booking %s", booking.get("id"))
    return web.json_response({"ok": True})


async def reschedule_booking(request):
    user = _user_from_request(request)
    if not _is_admin(user):
        raise web.HTTPForbidden(text="Admin access required")
    try:
        data = await request.json()
        booking_id = int(data["booking_id"])
        date, time, master = str(data["date"]), str(data["time"]), str(data["master"])
    except Exception:
        raise web.HTTPBadRequest(text="Invalid reschedule data")
    booking = await get_booking(booking_id)
    if not booking:
        raise web.HTTPNotFound(text="Booking not found")
    ok = await update_booking_details(booking_id, date, time, master)
    if not ok:
        raise web.HTTPConflict(text="Selected time is unavailable")
    updated = await get_booking(booking_id)
    if updated:
        try:
            await _notify_client(updated, event="rescheduled")
        except Exception:
            logging.exception("Failed to notify client %s about rescheduled booking %s", updated.get("user_id"), booking_id)
    return web.json_response({"ok": True, "booking": updated})


async def my_bookings(request):
    user = _user_from_request(request)
    return web.json_response({"ok": True, "bookings": await get_bookings_for_user(int(user["id"]))})


async def bookings(request):
    user = _user_from_request(request)
    if not _is_admin(user):
        raise web.HTTPForbidden(text="Admin access required")
    return web.json_response({"ok": True, "bookings": await get_all_bookings()})


async def master_bookings(request):
    user = _user_from_request(request)
    master = await get_master_by_telegram_id(int(user["id"]))
    if not master:
        raise web.HTTPForbidden(text="Master access is not configured")
    return web.json_response({"ok": True, "master": master, "bookings": await get_bookings_for_master(master["name_ru"])})

async def admin_set_master_telegram(request):
    user = _user_from_request(request)
    if not _is_admin(user): raise web.HTTPForbidden(text="Admin access required")
    data = await request.json()
    tid = int(data["telegram_id"]) if str(data.get("telegram_id","")).strip() else None
    await set_master_telegram_id(str(data["master_key"]), tid)
    return web.json_response({"ok": True})

async def admin_create_master(request):
    user=_user_from_request(request)
    if not _is_admin(user): raise web.HTTPForbidden(text="Admin access required")
    d=await request.json()
    key=str(d.get("key","")).strip(); ru=str(d.get("name_ru","")).strip(); uz=str(d.get("name_uz","")).strip()
    if not key or not ru or not uz: raise web.HTTPBadRequest(text="Master fields required")
    try: await add_master(key,ru,uz)
    except Exception as e: raise web.HTTPConflict(text=str(e))
    return web.json_response({"ok":True})

async def admin_delete_master(request):
    user=_user_from_request(request)
    if not _is_admin(user): raise web.HTTPForbidden(text="Admin access required")
    await deactivate_master(request.match_info["key"]); return web.json_response({"ok":True})

async def admin_create_service(request):
    user=_user_from_request(request)
    if not _is_admin(user): raise web.HTTPForbidden(text="Admin access required")
    d=await request.json()
    key=str(d.get("key","")).strip(); ru=str(d.get("name_ru","")).strip(); uz=str(d.get("name_uz","")).strip()
    price=str(d.get("price","")).strip(); duration=int(d.get("duration",30))
    if not key or not ru or not uz or not price or duration<5: raise web.HTTPBadRequest(text="Service fields required")
    try: await add_service(key,ru,uz,price,duration)
    except Exception as e: raise web.HTTPConflict(text=str(e))
    return web.json_response({"ok":True})

async def admin_update_service(request):
    user=_user_from_request(request)
    if not _is_admin(user): raise web.HTTPForbidden(text="Admin access required")
    d=await request.json(); await update_service(str(d["key"]),str(d["name_ru"]),str(d["name_uz"]),str(d["price"]),int(d["duration"]))
    return web.json_response({"ok":True})

async def admin_delete_service(request):
    user=_user_from_request(request)
    if not _is_admin(user): raise web.HTTPForbidden(text="Admin access required")
    await deactivate_service(request.match_info["key"]); return web.json_response({"ok":True})

async def admin_catalog(request):
    user = _user_from_request(request)
    if not _is_admin(user): raise web.HTTPForbidden(text="Admin access required")
    return web.json_response(await get_admin_catalog())

async def admin_toggle_link(request):
    user = _user_from_request(request)
    if not _is_admin(user): raise web.HTTPForbidden(text="Admin access required")
    data=await request.json()
    await set_master_service(str(data["service_key"]),str(data["master_key"]),bool(data.get("enabled")))
    return web.json_response({"ok":True})

async def admin_schedules(request):
    user = _user_from_request(request)
    if not _is_admin(user):
        raise web.HTTPForbidden(text="Admin access required")
    catalog = await get_admin_catalog()
    result = []
    for m in catalog["masters"]:
        result.append({"master": m, "schedule": [{"weekday": int(r[0]), "start": r[1], "end": r[2], "lunch_start": r[3], "lunch_end": r[4]} for r in await get_master_schedule(m["key"])]})
    return web.json_response({"ok": True, "masters": result})


async def admin_update_schedule(request):
    user = _user_from_request(request)
    if not _is_admin(user):
        raise web.HTTPForbidden(text="Admin access required")
    try:
        d = await request.json()
        master_key = str(d["master_key"]).strip()
        weekday = int(d["weekday"])
        start = str(d.get("start") or "").strip()
        end = str(d.get("end") or "").strip()
        lunch_start = str(d.get("lunch_start") or "").strip() or None
        lunch_end = str(d.get("lunch_end") or "").strip() or None
        if weekday < 0 or weekday > 6: raise ValueError
        if not start and not end:
            await set_master_day(master_key, weekday, None, None)
        else:
            datetime.strptime(start, "%H:%M"); datetime.strptime(end, "%H:%M")
            if start >= end: raise ValueError
            if (lunch_start is None) != (lunch_end is None): raise ValueError
            if lunch_start and lunch_end:
                datetime.strptime(lunch_start, "%H:%M"); datetime.strptime(lunch_end, "%H:%M")
                if not (start <= lunch_start < lunch_end <= end): raise ValueError
            await set_master_day(master_key, weekday, start, end, lunch_start, lunch_end)
    except Exception:
        raise web.HTTPBadRequest(text="Invalid schedule")
    return web.json_response({"ok": True})


async def admin_booking_filters(request):
    user = _user_from_request(request)
    if not _is_admin(user):
        raise web.HTTPForbidden(text="Admin access required")
    return web.json_response({"ok": True, "bookings": await get_bookings_filtered(
        date=request.query.get("date") or None,
        master=request.query.get("master") or None,
        status=request.query.get("status") or None,
        q=request.query.get("q") or None,
    ), "stats": await get_booking_stats()})


async def client_cancel_booking(request):
    user = _user_from_request(request)
    booking_id = int(request.match_info["booking_id"])
    booking = await get_booking(booking_id)
    if not booking or int(booking["user_id"]) != int(user["id"]):
        raise web.HTTPNotFound(text="Booking not found")
    if booking["status"] == "cancelled":
        return web.json_response({"ok": True, "booking": booking})
    if booking["status"] in {"completed", "no_show"}:
        raise web.HTTPConflict(text="Completed bookings cannot be cancelled")
    await update_booking_status(booking_id, "cancelled")
    updated = await get_booking(booking_id)
    if updated:
        try:
            await _notify_admin(updated)
        except Exception:
            logging.exception("Failed to notify admin about client cancellation %s", booking_id)
    return web.json_response({"ok": True, "booking": updated})


async def booking_detail(request):
    user = _user_from_request(request)
    booking = await get_booking(int(request.match_info["booking_id"]))
    if not booking:
        raise web.HTTPNotFound(text="Booking not found")
    if _is_admin(user):
        return web.json_response({"ok": True, "booking": booking})
    master = await get_master_by_telegram_id(int(user["id"]))
    if master and booking["master"] in {master.get("name_ru"), master.get("name_uz"), master.get("key")}:
        return web.json_response({"ok": True, "booking": booking})
    if int(booking["user_id"]) == int(user["id"]):
        return web.json_response({"ok": True, "booking": booking})
    raise web.HTTPForbidden(text="Access denied")


async def booking_status(request):
    user = _user_from_request(request)
    booking_id = int(request.match_info["booking_id"])
    is_admin = _is_admin(user)
    master = await get_master_by_telegram_id(int(user["id"]))
    booking = await get_booking(booking_id)
    if not booking:
        raise web.HTTPNotFound(text="Booking not found")
    if not is_admin and not master:
        raise web.HTTPForbidden(text="Staff access required")
    if master and not is_admin and booking["master"] not in {master.get("name_ru"), master.get("name_uz"), master.get("key")}:
        raise web.HTTPForbidden(text="Booking is not assigned to you")
    try:
        data = await request.json()
    except Exception:
        raise web.HTTPBadRequest(text="Invalid JSON")
    status = str(data.get("status", ""))
    master_statuses = {"completed", "no_show"}
    if master and not is_admin:
        if status not in master_statuses:
            raise web.HTTPForbidden(text="Masters may only set completed or no_show")
        comment = str(data.get("comment", "")).strip()[:1000]
        from database import update_booking_master_result
        if not await update_booking_master_result(booking_id, status, comment):
            raise web.HTTPBadRequest(text="Invalid master status")
    else:
        if status not in {"new", "confirmed", "cancelled", "in_progress", "completed", "no_show"}:
            raise web.HTTPBadRequest(text="Invalid status")
        if not await update_booking_status(booking_id, status):
            raise web.HTTPNotFound(text="Booking not found")
    updated = await get_booking(booking_id)
    if updated:
        try:
            if status in {"confirmed", "cancelled"}:
                await _notify_client(updated)
        except Exception:
            logging.exception("Failed to notify client %s about booking %s", updated.get("user_id"), booking_id)
    return web.json_response({"ok": True, "booking": updated})


async def index(request):
    return web.FileResponse(STATIC_DIR / "index.html")


def create_app():
    app = web.Application()
    app.router.add_get("/health", health)
    app.router.add_get("/maintenance", maintenance)
    app.router.add_get("/api/me", me)
    app.router.add_get("/api/catalog", catalog)
    app.router.add_post("/api/bookings", create_web_booking)
    app.router.add_get("/api/my-bookings", my_bookings)
    app.router.add_post("/api/admin/bookings/reschedule", reschedule_booking)
    app.router.add_get("/api/admin/bookings", bookings)
    app.router.add_get("/api/admin/bookings/{booking_id}", booking_detail)
    app.router.add_patch("/api/admin/bookings/{booking_id}/status", booking_status)
    app.router.add_get("/api/admin/bookings/filter", admin_booking_filters)
    app.router.add_get("/api/admin/catalog", admin_catalog)
    app.router.add_get("/api/admin/schedules", admin_schedules)
    app.router.add_patch("/api/admin/schedules", admin_update_schedule)
    app.router.add_get("/api/master/bookings", master_bookings)
    app.router.add_patch("/api/admin/master-telegram", admin_set_master_telegram)
    app.router.add_post("/api/admin/masters", admin_create_master)
    app.router.add_delete("/api/admin/masters/{key}", admin_delete_master)
    app.router.add_post("/api/admin/services", admin_create_service)
    app.router.add_patch("/api/admin/services/{key}", admin_update_service)
    app.router.add_delete("/api/admin/services/{key}", admin_delete_service)
    app.router.add_post("/api/admin/service-masters", admin_toggle_link)
    app.router.add_post("/api/my-bookings/{booking_id}/cancel", client_cancel_booking)
    app.router.add_get("/", index)
    app.router.add_static("/", STATIC_DIR, show_index=False)
    return app


async def start_webapp():
    runner = web.AppRunner(create_app())
    await runner.setup()
    await web.TCPSite(runner, os.getenv("WEBAPP_HOST", "0.0.0.0"), int(os.getenv("PORT") or os.getenv("WEBAPP_PORT", "8080"))).start()
    return runner
