from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from keyboards.inline import language_kb, main_menu
from locales.texts import t
from states import BookingStates
from database import get_salon_settings, get_services
import html

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(BookingStates.choosing_language)
    settings=await get_salon_settings()
    await message.answer(
        t("ru","welcome",salon_name=html.escape(settings.get("name","Ваш салон")),description=html.escape(settings.get("description",""))),
        reply_markup=language_kb()
    )


@router.callback_query(F.data.startswith("lang_"))
async def set_language(callback: CallbackQuery, state: FSMContext):
    lang = callback.data.split("_")[1]
    await state.update_data(lang=lang)
    await state.set_state(None)
    
    await callback.message.edit_text(t(lang, "main_menu"))
    await callback.message.answer(
        t(lang, "main_menu"),
        reply_markup=main_menu(lang)
    )
    await callback.answer()


@router.message(F.text.in_({"📋 Прайс", "📋 Narxlar"}))
async def show_price(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    settings = await get_salon_settings()
    services = await get_services()
    lines = []
    for s in services:
        name = s["name_ru"] if lang == "ru" else s["name_uz"]
        lines.append(f"• {name} — {s['price']}")
    await message.answer(t(lang, "price_list", salon_name=settings.get("name", "Ваш салон"), services="\n".join(lines)))


@router.message(F.text.in_({"📍 Адрес", "📍 Manzil"}))
async def show_address(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    settings = await get_salon_settings()
    await message.answer(t(lang, "address", address=settings.get("address", "—"), work_hours=settings.get("work_hours", "—")))


@router.message(F.text.in_({"📞 Контакты", "📞 Kontaktlar"}))
async def show_contacts(message: Message, state: FSMContext):
    data = await state.get_data()
    lang = data.get("lang", "ru")
    settings = await get_salon_settings()
    await message.answer(t(lang, "contacts", phone=settings.get("phone", "—"), telegram=settings.get("telegram", "—")))
