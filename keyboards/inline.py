from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from datetime import datetime, timedelta
from locales.texts import t


def language_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
            InlineKeyboardButton(text="🇺🇿 O‘zbek", callback_data="lang_uz")
        ]
    ])


def main_menu(lang: str):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(lang, "btn_book"))],
            [
                KeyboardButton(text=t(lang, "btn_price")),
                KeyboardButton(text=t(lang, "btn_address"))
            ],
            [KeyboardButton(text=t(lang, "btn_contacts"))]
        ],
        resize_keyboard=True
    )


async def services_kb(lang: str):
    from database import get_services
    services_rows = await get_services()
    services = {s["key"]: s["name_ru" if lang == "ru" else "name_uz"] for s in services_rows}
    buttons = [
        [InlineKeyboardButton(text=name, callback_data=f"service_{key}")]
        for key, name in services.items()
    ]
    buttons.append([InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


async def masters_kb(lang: str, service_key: str):
    from database import get_masters_for_service
    masters = await get_masters_for_service(service_key)
    buttons = []
    for master in masters:
        key = master["key"]
        name = master["name_ru"] if lang == "ru" else master["name_uz"]
        buttons.append([InlineKeyboardButton(text=name, callback_data=f"master_{key}")])
    buttons.append([InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="back_to_services")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def dates_kb(lang: str):
    buttons = []
    today = datetime.now()
    for i in range(1, 8):  # следующие 7 дней
        day = today + timedelta(days=i)
        date_str = day.strftime("%d.%m")
        weekday = day.strftime("%a")
        # Простая локализация дня недели
        weekdays = {
            "ru": {"Mon": "Пн", "Tue": "Вт", "Wed": "Ср", "Thu": "Чт", "Fri": "Пт", "Sat": "Сб", "Sun": "Вс"},
            "uz": {"Mon": "Du", "Tue": "Se", "Wed": "Cho", "Thu": "Pa", "Fri": "Ju", "Sat": "Sha", "Sun": "Ya"}
        }
        wd = weekdays.get(lang, weekdays["ru"]).get(weekday, weekday)
        buttons.append([InlineKeyboardButton(
            text=f"{date_str} ({wd})",
            callback_data=f"date_{date_str}"
        )])
    
    buttons.append([InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="back_to_services")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def times_kb(lang: str, available_times=None):
    times = available_times or ["10:00", "10:30", "11:00", "11:30", "12:00", "12:30",
             "13:00", "13:30", "14:00", "14:30", "15:00", "15:30",
             "16:00", "16:30", "17:00", "17:30", "18:00", "18:30", "19:00"]
    
    buttons = []
    row = []
    for i, time in enumerate(times):
        row.append(InlineKeyboardButton(text=time, callback_data=f"time_{time}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    
    buttons.append([InlineKeyboardButton(text=t(lang, "btn_back"), callback_data="back_to_dates")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def cancel_kb(lang: str):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t(lang, "btn_cancel"))]],
        resize_keyboard=True
    )


def phone_kb(lang: str):
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=t(lang, "btn_share_phone"), request_contact=True)],
            [KeyboardButton(text=t(lang, "btn_cancel"))]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
