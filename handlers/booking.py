from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from states import BookingStates
from keyboards.inline import services_kb, masters_kb, dates_kb, times_kb, main_menu, cancel_kb, phone_kb
from database import add_booking, is_slot_available, get_service, get_master, get_master_schedule, get_masters_for_service
from config import ADMIN_ID
from locales.texts import t
from salon_config import SALON
from datetime import datetime, timedelta

router = Router()


@router.message(F.text.in_({"📅 Записаться", "📅 Yozilish"}))
async def start_booking(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    
    await state.set_state(BookingStates.waiting_for_service)
    await message.answer(t(lang, "choose_service"), reply_markup=await services_kb(lang))


@router.callback_query(F.data.startswith("service_") & ~F.data.startswith("service_edit_") & ~F.data.startswith("service_off_") & (F.data != "service_add"))
async def process_service(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    
    service_key = callback.data.split("_")[1]
    service_row = await get_service(service_key)
    if not service_row:
        await callback.answer("Услуга недоступна", show_alert=True)
        return
    service_name = service_row["name_ru"] if lang == "ru" else service_row["name_uz"]
    
    available_masters = await get_masters_for_service(service_key)
    if not available_masters:
        await callback.answer("Для этой услуги пока нет назначенных мастеров", show_alert=True)
        return
    await state.update_data(service=service_name, service_key=service_key)
    await state.set_state(BookingStates.waiting_for_master)
    
    await callback.message.edit_text(
        f"{t(lang, 'choose_service')}\n\n✅ {service_name}\n\n{t(lang, 'choose_master')}",
        reply_markup=await masters_kb(lang, service_key)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("master_"))
async def process_master(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    master_key = callback.data.split("_", 1)[1]
    master_row = await get_master(master_key)
    if not master_row:
        await callback.answer("Мастер недоступен", show_alert=True)
        return
    master = master_row["name_ru"] if lang == "ru" else master_row["name_uz"]
    await state.update_data(master=master, master_key=master_key)
    await state.set_state(BookingStates.waiting_for_date)

    await callback.message.edit_text(
        f"✅ {data.get('service')}\n👩‍🎨 {master}\n\n{t(lang, 'choose_date')}",
        reply_markup=dates_kb(lang)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("date_"))
async def process_date(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    
    date = callback.data.split("_")[1]
    master_key = data.get("master_key")
    schedule_rows = await get_master_schedule(master_key)
    schedule = {weekday: [[start, end]] for weekday, start, end in schedule_rows}
    parsed = datetime.strptime(date, "%d.%m")
    year = datetime.now().year
    selected_date = parsed.replace(year=year)
    weekday = selected_date.weekday()
    ranges = schedule.get(weekday, [])
    available = []
    service_key = data.get("service_key")
    service_row = await get_service(service_key)
    duration = service_row["duration"] if service_row else 30
    for start, end in ranges:
        cur = datetime.strptime(start, "%H:%M")
        finish = datetime.strptime(end, "%H:%M")
        while cur < finish:
            slot = cur.strftime("%H:%M")
            if cur + timedelta(minutes=duration) <= finish and await is_slot_available(date, slot, duration, data.get("master")):
                available.append(slot)
            cur += timedelta(minutes=30)

    await state.update_data(date=date)
    await state.set_state(BookingStates.waiting_for_time)
    
    await callback.message.edit_text(
        f"✅ {data.get('service')}\n👩‍🎨 {data.get('master')}\n📅 {date}\n\n{t(lang, 'choose_time')}",
        reply_markup=times_kb(lang, available)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("time_"))
async def process_time(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    
    time = callback.data.split("_")[1]
    await state.update_data(time=time)
    await state.set_state(BookingStates.waiting_for_name)
    
    await callback.message.edit_text(
        f"✅ {data.get('service')}\n📅 {data.get('date')}  {time}\n\n{t(lang, 'enter_name')}"
    )
    await callback.message.answer(t(lang, "enter_name"), reply_markup=cancel_kb(lang))
    await callback.answer()


@router.message(BookingStates.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    
    if message.text in [t("ru", "btn_cancel"), t("uz", "btn_cancel")]:
        await state.set_state(None)
        await message.answer(t(lang, "booking_cancelled"), reply_markup=main_menu(lang))
        return
    
    await state.update_data(name=message.text)
    await state.set_state(BookingStates.waiting_for_phone)
    await message.answer(t(lang, "enter_phone"), reply_markup=phone_kb(lang))


@router.message(BookingStates.waiting_for_phone)
async def process_phone(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    
    if message.text in [t("ru", "btn_cancel"), t("uz", "btn_cancel")]:
        await state.set_state(None)
        await message.answer(t(lang, "booking_cancelled"), reply_markup=main_menu(lang))
        return
    
    if message.contact:
        if message.contact.user_id and message.contact.user_id != message.from_user.id:
            await message.answer(t(lang, "phone_must_be_self"), reply_markup=phone_kb(lang))
            return
        phone = message.contact.phone_number
    else:
        phone = (message.text or "").strip()
        if not phone:
            await message.answer(t(lang, "phone_invalid"), reply_markup=phone_kb(lang))
            return

    name = data.get("name")
    service = data.get("service")
    date = data.get("date")
    time = data.get("time")
    master = data.get("master")
    service_key = data.get("service_key")
    service_row = await get_service(service_key)
    duration = service_row["duration"] if service_row else 30

    # Final availability check immediately before saving the booking.
    if not await is_slot_available(date, time, duration, master):
        await message.answer(t(lang, "slot_taken"), reply_markup=main_menu(lang))
        await state.set_state(None)
        return
    
    saved = await add_booking(
        user_id=message.from_user.id,
        username=message.from_user.username or "",
        service=service,
        master=master,
        date=date,
        time=time,
        name=name,
        phone=phone,
        lang=lang,
        duration=duration
    )
    
    if not saved:
        await message.answer(t(lang, "slot_taken"), reply_markup=main_menu(lang))
        await state.set_state(None)
        return
    
    # Уведомление админу
    text_admin = (
        f"🆕 <b>Новая запись!</b>\n\n"
        f"Услуга: {service}\n"
        f"Мастер: {master}\n"
        f"Дата: {date}\n"
        f"Время: {time}\n"
        f"Имя: {name}\n"
        f"Телефон: {phone}\n"
        f"Язык: {lang}\n"
        f"Username: @{message.from_user.username or 'нет'}"
    )
    try:
        await message.bot.send_message(ADMIN_ID, text_admin)
    except Exception:
        pass
    
    await message.answer(
        t(lang, "booking_success", service=service, date=date, time=time, name=name, phone=phone),
        reply_markup=main_menu(lang)
    )
    await state.set_state(None)


@router.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    await state.set_state(None)
    await callback.message.delete()
    await callback.message.answer(t(lang, "main_menu"), reply_markup=main_menu(lang))
    await callback.answer()


@router.callback_query(F.data == "back_to_services")
async def back_to_services(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    await state.set_state(BookingStates.waiting_for_service)
    await callback.message.edit_text(t(lang, "choose_service"), reply_markup=await services_kb(lang))
    await callback.answer()


@router.callback_query(F.data == "back_to_dates")
async def back_to_dates(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    await state.set_state(BookingStates.waiting_for_date)
    await callback.message.edit_text(
        f"✅ {data.get('service')}\n\n{t(lang, 'choose_date')}",
        reply_markup=dates_kb(lang)
    )
    await callback.answer()
