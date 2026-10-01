from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from io import BytesIO
import aiohttp
import json
from aiogram.filters import Command
from config import ADMIN_ID, SETUP_COMMAND
from states import AdminStates
from aiogram.fsm.context import FSMContext
from datetime import datetime
from database import get_all_bookings, update_booking_status, get_booking, get_services, get_masters, get_masters_for_service, get_services_for_master, set_master_service, get_service, add_service, update_service, deactivate_service, add_master, deactivate_master, set_master_day, get_master_schedule, get_salon_settings, set_salon_setting

router = Router()


def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Сегодня", callback_data="admin_today"),
         InlineKeyboardButton(text="📆 Завтра", callback_data="admin_tomorrow")],
        [InlineKeyboardButton(text="📋 Все записи", callback_data="admin_all")],
        [InlineKeyboardButton(text="💇 Услуги", callback_data="catalog_services"),
         InlineKeyboardButton(text="👩‍🎨 Мастера", callback_data="catalog_masters")],
        [InlineKeyboardButton(text="➕ Добавить услугу", callback_data="service_add"),
         InlineKeyboardButton(text="➕ Добавить мастера", callback_data="master_add")],
        [InlineKeyboardButton(text="🕐 Расписание", callback_data="schedule_list")],
        [InlineKeyboardButton(text="⚙️ Настройка салона", callback_data="salon_setup")],
        [InlineKeyboardButton(text="🤖 Настройки бота", callback_data="bot_settings")],
        [InlineKeyboardButton(text="🏠 В главное меню", callback_data="admin_exit")]
    ])


def booking_actions(booking_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"booking_confirm_{booking_id}"),
            InlineKeyboardButton(text="❌ Отменить", callback_data=f"booking_cancel_{booking_id}")
        ]
    ])


def format_booking(b):
    status = {"new": "🆕 Новая", "confirmed": "✅ Подтверждена", "cancelled": "❌ Отменена"}.get(b.get("status"), b.get("status", "new"))
    return (
        f"#{b['id']} | <b>{b['service']}</b>\n"
        f"👩‍🎨 {b.get('master', '—')}\n"
        f"📅 {b['date']}  🕐 {b['time']}\n"
        f"👤 {b['name']}\n"
        f"📱 {b['phone']}\n"
        f"{status}"
    )


@router.callback_query(F.data == "admin_exit", F.from_user.id == ADMIN_ID)
async def admin_exit(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "🏠 <b>Главное меню</b>",
        reply_markup=None
    )
    await callback.answer("Вы вышли из панели записей")


@router.message(Command("bookings"), F.from_user.id == ADMIN_ID)
async def show_bookings(message: Message):
    await message.answer("⚙️ <b>Панель записей</b>", reply_markup=admin_kb())


async def send_filtered(message: Message, mode: str):
    from datetime import datetime, timedelta
    bookings = await get_all_bookings()
    today = datetime.now()
    target = today if mode == "today" else today + timedelta(days=1)
    target_str = target.strftime("%d.%m")
    selected = bookings[:30] if mode == "all" else [b for b in bookings if b["date"] == target_str]
    if not selected:
        await message.answer("Записей нет.")
        return
    for b in selected:
        await message.answer(format_booking(b), reply_markup=booking_actions(b["id"]))


@router.callback_query(F.data.in_({"admin_today", "admin_tomorrow", "admin_all"}), F.from_user.id == ADMIN_ID)
async def admin_filter(callback: CallbackQuery):
    mode = {"admin_today": "today", "admin_tomorrow": "tomorrow", "admin_all": "all"}[callback.data]
    await send_filtered(callback.message, mode)
    await callback.answer()


@router.callback_query(F.data.startswith("booking_confirm_"), F.from_user.id == ADMIN_ID)
async def confirm_booking(callback: CallbackQuery):
    booking_id = int(callback.data.rsplit("_", 1)[1])
    booking = await get_booking(booking_id)
    if not booking:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    await update_booking_status(booking_id, "confirmed")
    await callback.message.edit_reply_markup(reply_markup=None)
    try:
        await callback.bot.send_message(
            booking["user_id"],
            f"✅ <b>Ваша запись подтверждена!</b>\n\n"
            f"{booking['service']}\n"
            f"👩‍🎨 {booking.get('master', '—')}\n"
            f"📅 {booking['date']}  🕐 {booking['time']}"
        )
    except Exception:
        pass
    await callback.answer("Подтверждено")


@router.callback_query(F.data.startswith("booking_cancel_"), F.from_user.id == ADMIN_ID)
async def cancel_booking(callback: CallbackQuery):
    booking_id = int(callback.data.rsplit("_", 1)[1])
    booking = await get_booking(booking_id)
    if not booking:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    await update_booking_status(booking_id, "cancelled")
    await callback.message.edit_reply_markup(reply_markup=None)
    try:
        await callback.bot.send_message(
            booking["user_id"],
            f"❌ <b>Ваша запись отменена.</b>\n\n"
            f"{booking['service']}\n"
            f"👩‍🎨 {booking.get('master', '—')}\n"
            f"📅 {booking['date']}  🕐 {booking['time']}"
        )
    except Exception:
        pass
    await callback.answer("Отменено")


@router.callback_query(F.data == "catalog_services", F.from_user.id == ADMIN_ID)
async def catalog_services(callback: CallbackQuery):
    services = await get_services()
    if not services:
        await callback.message.answer("Услуг пока нет.")
    for s in services:
        await callback.message.answer(
            f"💇 <b>{s['name_ru']}</b> / {s['name_uz']}\n"
            f"💰 {s['price']} • ⏱ {s['duration']} мин.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"service_edit_{s['key']}"), InlineKeyboardButton(text="🗑 Отключить", callback_data=f"service_off_{s['key']}")
            ]])
        )
    await callback.answer()

@router.callback_query(F.data == "catalog_masters", F.from_user.id == ADMIN_ID)
async def catalog_masters(callback: CallbackQuery):
    masters = await get_masters()
    if not masters:
        await callback.message.answer("Мастеров пока нет.")
    for m in masters:
        await callback.message.answer(
            f"👩‍🎨 <b>{m['name_ru']}</b> / {m['name_uz']}",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="💇 Услуги", callback_data=f"master_services_{m['key']}"), InlineKeyboardButton(text="🗑 Отключить", callback_data=f"master_off_{m['key']}")
            ]])
        )
    await callback.answer()

@router.callback_query(F.data.startswith("service_edit_"), F.from_user.id == ADMIN_ID)
async def service_edit_start(callback: CallbackQuery, state: FSMContext):
    key = callback.data[len("service_edit_"):]
    service = await get_service(key)
    if not service:
        await callback.answer("Услуга не найдена", show_alert=True)
        return
    await state.update_data(edit_service_key=key)
    await state.set_state(AdminStates.editing_service_ru)
    await callback.message.answer(
        f"✏️ Редактирование услуги\n\n"
        f"🇷🇺 Текущее название: <b>{service['name_ru']}</b>\n"
        "Введите новое название на русском:"
    )
    await callback.answer()


@router.message(AdminStates.editing_service_ru, F.from_user.id == ADMIN_ID)
async def service_edit_ru(message: Message, state: FSMContext):
    await state.update_data(name_ru=message.text.strip())
    await state.set_state(AdminStates.editing_service_uz)
    await message.answer("Введите новое название на узбекском:")


@router.message(AdminStates.editing_service_uz, F.from_user.id == ADMIN_ID)
async def service_edit_uz(message: Message, state: FSMContext):
    await state.update_data(name_uz=message.text.strip())
    await state.set_state(AdminStates.editing_service_price)
    await message.answer("Введите новую цену (например: 120 000 сум):")


@router.message(AdminStates.editing_service_price, F.from_user.id == ADMIN_ID)
async def service_edit_price(message: Message, state: FSMContext):
    await state.update_data(price=message.text.strip())
    await state.set_state(AdminStates.editing_service_duration)
    await message.answer("Введите новую длительность в минутах (например: 60):")


@router.message(AdminStates.editing_service_duration, F.from_user.id == ADMIN_ID)
async def service_edit_duration(message: Message, state: FSMContext):
    try:
        duration = int(message.text.strip())
        if duration < 5 or duration > 600:
            raise ValueError
    except ValueError:
        await message.answer("Введите число минут от 5 до 600.")
        return
    data = await state.get_data()
    await update_service(
        data["edit_service_key"],
        data["name_ru"],
        data["name_uz"],
        data["price"],
        duration,
    )
    await state.clear()
    await message.answer("✅ Услуга обновлена.", reply_markup=admin_kb())
    await catalog_services_from_message(message)


async def catalog_services_from_message(message: Message):
    services = await get_services()
    await message.answer("💇 <b>Услуги</b>")
    for s in services:
        await message.answer(
            f"💇 <b>{s['name_ru']}</b> / {s['name_uz']}\n"
            f"💰 {s['price']} • ⏱ {s['duration']} мин.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"service_edit_{s['key']}"),
                InlineKeyboardButton(text="🗑 Отключить", callback_data=f"service_off_{s['key']}")
            ]])
        )


@router.callback_query(F.data.startswith("service_off_"), F.from_user.id == ADMIN_ID)
async def service_off(callback: CallbackQuery):
    await deactivate_service(callback.data[len("service_off_"):])
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Услуга отключена")

@router.callback_query(F.data.startswith("master_off_"), F.from_user.id == ADMIN_ID)
async def master_off(callback: CallbackQuery):
    await deactivate_master(callback.data[len("master_off_"):])
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.answer("Мастер отключён")


@router.callback_query(F.data == "service_add", F.from_user.id == ADMIN_ID)
async def service_add_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.adding_service_ru)
    await callback.message.answer("Введите название услуги на русском:")
    await callback.answer()

@router.message(AdminStates.adding_service_ru, F.from_user.id == ADMIN_ID)
async def service_ru(message: Message, state: FSMContext):
    await state.update_data(name_ru=message.text.strip())
    await state.set_state(AdminStates.adding_service_uz)
    await message.answer("Введите название услуги на узбекском:")

@router.message(AdminStates.adding_service_uz, F.from_user.id == ADMIN_ID)
async def service_uz(message: Message, state: FSMContext):
    await state.update_data(name_uz=message.text.strip())
    await state.set_state(AdminStates.adding_service_price)
    await message.answer("Введите цену (например: 120 000 сум):")

@router.message(AdminStates.adding_service_price, F.from_user.id == ADMIN_ID)
async def service_price(message: Message, state: FSMContext):
    await state.update_data(price=message.text.strip())
    await state.set_state(AdminStates.adding_service_duration)
    await message.answer("Введите длительность в минутах (например: 60):")

@router.message(AdminStates.adding_service_duration, F.from_user.id == ADMIN_ID)
async def service_duration(message: Message, state: FSMContext):
    try:
        duration=int(message.text.strip())
        if duration < 5 or duration > 600: raise ValueError
    except ValueError:
        await message.answer("Введите число минут от 5 до 600.")
        return
    data=await state.get_data()
    key="service_"+str(abs(hash(data["name_ru"])) % 1000000)
    await add_service(key,data["name_ru"],data["name_uz"],data["price"],duration)
    await state.clear()
    await message.answer("✅ Услуга добавлена.", reply_markup=admin_kb())

@router.callback_query(F.data == "master_add", F.from_user.id == ADMIN_ID)
async def master_add_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.adding_master_ru)
    await callback.message.answer("Введите имя мастера на русском:")
    await callback.answer()

@router.message(AdminStates.adding_master_ru, F.from_user.id == ADMIN_ID)
async def master_ru(message: Message, state: FSMContext):
    await state.update_data(name_ru=message.text.strip())
    await state.set_state(AdminStates.adding_master_uz)
    await message.answer("Введите имя мастера на узбекском:")

@router.message(AdminStates.adding_master_uz, F.from_user.id == ADMIN_ID)
async def master_uz(message: Message, state: FSMContext):
    data=await state.get_data()
    key="master_"+str(abs(hash(data["name_ru"])) % 1000000)
    await add_master(key,data["name_ru"],message.text.strip())
    await state.clear()
    await message.answer("✅ Мастер добавлен. Расписание настроим следующим шагом.", reply_markup=admin_kb())


@router.callback_query(F.data.startswith("master_services_"), F.from_user.id == ADMIN_ID)
async def master_services(callback: CallbackQuery):
    master_key = callback.data[len("master_services_"):]
    master = await get_master(master_key)
    if not master:
        await callback.answer("Мастер не найден", show_alert=True)
        return
    services = await get_services()
    assigned = {s["key"] for s in await get_services_for_master(master_key)}
    rows = []
    for s in services:
        mark = "☑️" if s["key"] in assigned else "⬜"
        rows.append([InlineKeyboardButton(text=f"{mark} {s['name_ru']}", callback_data=f"svcmasters:{master_key}:{s['key']}")])
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="catalog_masters")])
    await callback.message.answer(
        f"🔗 <b>Услуги мастера: {master['name_ru']}</b>\n\nНажимайте на услугу, чтобы назначить или снять её.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("svcmasters:"), F.from_user.id == ADMIN_ID)
async def toggle_master_service(callback: CallbackQuery):
    payload = callback.data[len("svcmasters:"):]
    try:
        master_key, service_key = payload.split(":", 1)
    except ValueError:
        await callback.answer("Некорректная услуга", show_alert=True)
        return
    assigned = {s["key"] for s in await get_services_for_master(master_key)}
    await set_master_service(service_key, master_key, service_key not in assigned)
    services = await get_services()
    assigned = {s["key"] for s in await get_services_for_master(master_key)}
    rows = []
    for s in services:
        mark = "☑️" if s["key"] in assigned else "⬜"
        rows.append([InlineKeyboardButton(text=f"{mark} {s['name_ru']}", callback_data=f"svcmasters:{master_key}:{s['key']}")])
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="catalog_masters")])
    await callback.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await callback.answer("Сохранено")


@router.callback_query(F.data == "schedule_list", F.from_user.id == ADMIN_ID)
async def schedule_list(callback: CallbackQuery):
    masters = await get_masters()
    for m in masters:
        await callback.message.answer(
            f"🕐 Расписание: <b>{m['name_ru']}</b>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Пн", callback_data=f"sched_{m['key']}_0"),
                 InlineKeyboardButton(text="Вт", callback_data=f"sched_{m['key']}_1"),
                 InlineKeyboardButton(text="Ср", callback_data=f"sched_{m['key']}_2"),
                 InlineKeyboardButton(text="Чт", callback_data=f"sched_{m['key']}_3")],
                [InlineKeyboardButton(text="Пт", callback_data=f"sched_{m['key']}_4"),
                 InlineKeyboardButton(text="Сб", callback_data=f"sched_{m['key']}_5"),
                 InlineKeyboardButton(text="Вс", callback_data=f"sched_{m['key']}_6")]
            ])
        )
    await callback.answer()

@router.callback_query(F.data.startswith("sched_"), F.from_user.id == ADMIN_ID)
async def schedule_day(callback: CallbackQuery, state: FSMContext):
    _, key, weekday = callback.data.split("_", 2)
    await state.update_data(schedule_master=key, schedule_weekday=int(weekday))
    await callback.message.answer("Введите часы работы, например <b>10:00-20:00</b>. Для выходного напишите <b>выходной</b>.")
    await state.set_state(AdminStates.adding_master_confirm)
    await callback.answer()

@router.message(AdminStates.adding_master_confirm, F.from_user.id == ADMIN_ID)
async def schedule_save(message: Message, state: FSMContext):
    value=message.text.strip().lower()
    data=await state.get_data()
    if value in ("выходной","выходной день","off"):
        await set_master_day(data["schedule_master"], data["schedule_weekday"], None, None)
    else:
        try:
            start,end=[x.strip() for x in value.split("-",1)]
            datetime.strptime(start,"%H:%M")
            datetime.strptime(end,"%H:%M")
        except Exception:
            await message.answer("Формат: 10:00-20:00 или «выходной».")
            return
        await set_master_day(data["schedule_master"], data["schedule_weekday"], start, end)
    await state.clear()
    await message.answer("✅ Расписание сохранено.", reply_markup=admin_kb())


def bot_settings_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить имя", callback_data="bot_name")],
        [InlineKeyboardButton(text="📝 Изменить описание", callback_data="bot_description")],
        [InlineKeyboardButton(text="🖼 Изменить фото", callback_data="bot_photo")],
        [InlineKeyboardButton(text="🔗 Изменить username", callback_data="bot_username_info")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="bot_settings_back")]
    ])


async def show_bot_settings(message: Message):
    me = await message.bot.get_me()
    try:
        short = await message.bot.get_my_short_description()
        description = short.short_description or "—"
    except Exception:
        description = "—"
    await message.answer(
        "🤖 <b>Настройки бота</b>\n\n"
        f"👤 Имя: <b>{me.full_name}</b>\n"
        f"🔗 Username: @{me.username or '—'}\n"
        f"📝 Описание: {description}",
        reply_markup=bot_settings_kb()
    )


@router.message(Command("bot_settings"), F.from_user.id == ADMIN_ID)
async def bot_settings_command(message: Message, state: FSMContext):
    await state.clear()
    await show_bot_settings(message)


@router.callback_query(F.data == "bot_settings", F.from_user.id == ADMIN_ID)
async def bot_settings_button(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_bot_settings(callback.message)
    await callback.answer()


@router.callback_query(F.data == "bot_settings_back", F.from_user.id == ADMIN_ID)
async def bot_settings_back(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("⚙️ <b>Панель записей</b>", reply_markup=admin_kb())
    await callback.answer()


@router.callback_query(F.data == "bot_name", F.from_user.id == ADMIN_ID)
async def bot_name_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.bot_name)
    await callback.message.answer("✏️ Введите новое имя бота (до 64 символов):")
    await callback.answer()


@router.message(AdminStates.bot_name, F.from_user.id == ADMIN_ID)
async def bot_name_save(message: Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name or len(name) > 64:
        await message.answer("Имя должно быть от 1 до 64 символов.")
        return
    await message.bot.set_my_name(name=name)
    await state.clear()
    await message.answer("✅ Имя бота изменено.")
    await show_bot_settings(message)


@router.callback_query(F.data == "bot_description", F.from_user.id == ADMIN_ID)
async def bot_description_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.bot_description)
    await callback.message.answer("📝 Введите описание бота (до 120 символов). Оно будет отображаться в профиле под аватаркой:")
    await callback.answer()


@router.message(AdminStates.bot_description, F.from_user.id == ADMIN_ID)
async def bot_description_save(message: Message, state: FSMContext):
    description = (message.text or "").strip()
    if len(description) > 120:
        await message.answer("Описание профиля должно быть не длиннее 120 символов.")
        return
    await message.bot.set_my_short_description(short_description=description)
    await message.bot.set_my_description(description=description)
    await state.clear()
    await message.answer("✅ Описание бота изменено.")
    await show_bot_settings(message)


@router.callback_query(F.data == "bot_username_info", F.from_user.id == ADMIN_ID)
async def bot_username_info(callback: CallbackQuery):
    await callback.answer(
        "Username бота нельзя менять через Bot API. Его нужно изменить через @BotFather. "
        "После изменения здесь автоматически будет показан новый username.",
        show_alert=True
    )


async def set_bot_profile_photo(bot, image_bytes: bytes, filename: str = "avatar.jpg"):
    # Telegram Bot API requires an uploaded InputProfilePhoto; using the raw API here
    # keeps compatibility with the project's currently pinned aiogram version.
    from config import BOT_TOKEN
    form = aiohttp.FormData()
    form.add_field(
        "photo",
        json.dumps({"type": "static", "photo": "attach://profile_photo"}),
        content_type="application/json",
    )
    form.add_field(
        "profile_photo",
        image_bytes,
        filename=filename,
        content_type="image/jpeg",
    )
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/setMyProfilePhoto"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=form, timeout=30) as response:
            data = await response.json()
            if not data.get("ok"):
                raise RuntimeError(data.get("description", "Telegram API error"))


@router.callback_query(F.data == "bot_photo", F.from_user.id == ADMIN_ID)
async def bot_photo_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.bot_photo)
    await callback.message.answer("🖼 Отправьте новую фотографию бота одним сообщением:")
    await callback.answer()


@router.message(AdminStates.bot_photo, F.photo, F.from_user.id == ADMIN_ID)
async def bot_photo_save(message: Message, state: FSMContext):
    try:
        photo = message.photo[-1]
        file = await message.bot.get_file(photo.file_id)
        buffer = BytesIO()
        await message.bot.download_file(file.file_path, destination=buffer)
        await set_bot_profile_photo(message.bot, buffer.getvalue(), "avatar.jpg")
        await state.clear()
        await message.answer("✅ Фото бота изменено.")
        await show_bot_settings(message)
    except Exception as exc:
        await message.answer(f"❌ Не удалось изменить фото: {exc}")


@router.message(AdminStates.bot_photo, F.from_user.id == ADMIN_ID)
async def bot_photo_wrong(message: Message):
    await message.answer("Пожалуйста, отправьте именно фотографию.")



def salon_setup_kb(settings):
    def value(key, default="—"):
        v = settings.get(key)
        return v if v else default

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"🏷 Название: {value('name')}", callback_data="setup_name")],
        [InlineKeyboardButton(text=f"📝 Описание: {value('description')}", callback_data="setup_description")],
        [InlineKeyboardButton(text=f"📍 Адрес: {value('address')}", callback_data="setup_address")],
        [InlineKeyboardButton(text=f"📞 Телефон: {value('phone')}", callback_data="setup_phone")],
        [InlineKeyboardButton(text=f"📱 Telegram: {value('telegram')}", callback_data="setup_telegram")],
        [InlineKeyboardButton(text=f"📸 Instagram: {value('instagram')}", callback_data="setup_instagram")],
        [InlineKeyboardButton(text="💰 Валюта: UZS — узбекский сум", callback_data="setup_currency_info")],
        [InlineKeyboardButton(text="🌍 Часовой пояс: GMT+5 — Ташкент", callback_data="setup_timezone_info")],
        [InlineKeyboardButton(text="💾 Сохранить", callback_data="setup_save"),
         InlineKeyboardButton(text="❌ Отмена", callback_data="setup_cancel")]
    ])


async def show_salon_setup(message: Message):
    settings = await get_salon_settings()
    await message.answer(
        "🔐 <b>Настройка салона</b>\n\n"
        "Выберите поле, которое хотите изменить.\n"
        "Валюта и часовой пояс установлены автоматически.",
        reply_markup=salon_setup_kb(settings)
    )


async def open_salon_setup(message: Message, state: FSMContext):
    await state.clear()
    await set_salon_setting("currency", "UZS")
    await set_salon_setting("timezone", "Asia/Tashkent")
    await show_salon_setup(message)


@router.message(Command("salon_setup"), F.from_user.id == ADMIN_ID)
async def private_setup_start(message: Message, state: FSMContext):
    await open_salon_setup(message, state)


@router.message(F.text == SETUP_COMMAND, F.from_user.id == ADMIN_ID)
async def private_setup_start_legacy(message: Message, state: FSMContext):
    await open_salon_setup(message, state)


@router.callback_query(F.data == "salon_setup", F.from_user.id == ADMIN_ID)
async def salon_setup_button(callback: CallbackQuery, state: FSMContext):
    await open_salon_setup(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "setup_name", F.from_user.id == ADMIN_ID)
async def setup_name_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.setup_name)
    await callback.message.answer("🏷 Введите название салона:")
    await callback.answer()


@router.message(AdminStates.setup_name, F.from_user.id == ADMIN_ID)
async def setup_name(message: Message, state: FSMContext):
    await set_salon_setting("name", message.text.strip())
    await state.clear()
    await show_salon_setup(message)


@router.callback_query(F.data == "setup_description", F.from_user.id == ADMIN_ID)
async def setup_description_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.setup_description)
    await callback.message.answer("📝 Введите описание салона:")
    await callback.answer()


@router.message(AdminStates.setup_description, F.from_user.id == ADMIN_ID)
async def setup_description(message: Message, state: FSMContext):
    await set_salon_setting("description", message.text.strip())
    await state.clear()
    await show_salon_setup(message)


@router.callback_query(F.data == "setup_address", F.from_user.id == ADMIN_ID)
async def setup_address_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.setup_address)
    await callback.message.answer("📍 Введите адрес салона:")
    await callback.answer()


@router.message(AdminStates.setup_address, F.from_user.id == ADMIN_ID)
async def setup_address(message: Message, state: FSMContext):
    await set_salon_setting("address", message.text.strip())
    await state.clear()
    await show_salon_setup(message)


@router.callback_query(F.data == "setup_phone", F.from_user.id == ADMIN_ID)
async def setup_phone_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.setup_phone)
    await callback.message.answer("📞 Введите номер телефона:")
    await callback.answer()


@router.message(AdminStates.setup_phone, F.from_user.id == ADMIN_ID)
async def setup_phone(message: Message, state: FSMContext):
    await set_salon_setting("phone", message.text.strip())
    await state.clear()
    await show_salon_setup(message)


@router.callback_query(F.data == "setup_telegram", F.from_user.id == ADMIN_ID)
async def setup_telegram_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.setup_telegram)
    await callback.message.answer("📱 Введите Telegram салона:")
    await callback.answer()


@router.message(AdminStates.setup_telegram, F.from_user.id == ADMIN_ID)
async def setup_telegram(message: Message, state: FSMContext):
    await set_salon_setting("telegram", message.text.strip())
    await state.clear()
    await show_salon_setup(message)


@router.callback_query(F.data == "setup_instagram", F.from_user.id == ADMIN_ID)
async def setup_instagram_start(callback: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.setup_instagram)
    await callback.message.answer("📸 Введите Instagram салона:")
    await callback.answer()


@router.message(AdminStates.setup_instagram, F.from_user.id == ADMIN_ID)
async def setup_instagram(message: Message, state: FSMContext):
    await set_salon_setting("instagram", message.text.strip())
    await state.clear()
    await show_salon_setup(message)


@router.callback_query(F.data == "setup_currency_info", F.from_user.id == ADMIN_ID)
async def setup_currency_info(callback: CallbackQuery):
    await callback.answer("Валюта фиксирована: UZS — узбекский сум", show_alert=True)


@router.callback_query(F.data == "setup_timezone_info", F.from_user.id == ADMIN_ID)
async def setup_timezone_info(callback: CallbackQuery):
    await callback.answer("Часовой пояс фиксирован: GMT+5 — Asia/Tashkent", show_alert=True)


@router.callback_query(F.data == "setup_save", F.from_user.id == ADMIN_ID)
async def setup_save(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    settings = await get_salon_settings()
    await callback.message.edit_text(
        "✅ <b>Настройки салона сохранены.</b>\n\n"
        f"🏷 <b>{settings.get('name', 'Без названия')}</b>\n"
        f"📝 {settings.get('description', 'Описание не указано')}\n"
        f"📍 {settings.get('address', 'Адрес не указан')}\n"
        f"📞 {settings.get('phone', 'Телефон не указан')}\n"
        f"📱 Telegram: {settings.get('telegram', '—')}\n"
        f"📸 Instagram: {settings.get('instagram', '—')}\n"
        "💰 UZS — узбекский сум\n"
        "🌍 GMT+5 — Ташкент",
        reply_markup=admin_kb()
    )
    await callback.answer("Сохранено")


@router.callback_query(F.data == "setup_cancel", F.from_user.id == ADMIN_ID)
async def setup_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("⚙️ <b>Панель записей</b>", reply_markup=admin_kb())
    await callback.answer()
