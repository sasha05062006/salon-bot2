from salon_config import SALON


TEXTS = {
    "ru": {
        "welcome": "👋 Добро пожаловать в <b>{salon_name}</b>!\n\n{description}\n\nВыберите язык / Tilni tanlang:",
        "choose_lang": "Выберите язык:",
        "main_menu": "Главное меню:",
        "btn_book": "📅 Записаться",
        "btn_price": "📋 Прайс",
        "btn_address": "📍 Адрес",
        "btn_contacts": "📞 Контакты",
        "btn_back": "« Назад",
        "btn_cancel": "❌ Отмена",
        "btn_share_phone": "📱 Отправить номер телефона",
        "phone_invalid": "Пожалуйста, отправьте номер телефона кнопкой ниже или введите его вручную.",
        "phone_must_be_self": "Пожалуйста, отправьте свой номер телефона.",
        "slot_taken": "⚠️ К сожалению, это время уже заняли. Пожалуйста, выберите другое время.",
        "choose_service": "Выберите услугу:",
        "choose_master": "Выберите мастера:",
        "choose_date": "Выберите дату:",
        "choose_time": "Выберите время:",
        "enter_name": "Введите ваше имя:",
        "enter_phone": "Введите номер телефона:",
        "booking_success": "✅ Запись успешно создана!\n\nУслуга: <b>{service}</b>\nДата: {date}\nВремя: {time}\nИмя: {name}\nТелефон: {phone}\n\nМы свяжемся с вами для подтверждения.",
        "booking_cancelled": "Запись отменена.",
        "price_list": "<b>Прайс-лист {salon_name}:</b>\n\n{services}",
        "address": "📍 <b>Адрес:</b> {address}\n\n🕐 <b>Режим работы:</b> {work_hours}",
        "contacts": "📞 <b>Телефон:</b> {phone}\nTelegram: {telegram}",
    },
    "uz": {
        "welcome": "👋 <b>{salon_name}</b> saloniga xush kelibsiz!\n\n{description}\n\nTilni tanlang / Выберите язык:",
        "choose_lang": "Tilni tanlang:",
        "main_menu": "Asosiy menyu:",
        "btn_book": "📅 Yozilish",
        "btn_price": "📋 Narxlar",
        "btn_address": "📍 Manzil",
        "btn_contacts": "📞 Kontaktlar",
        "btn_back": "« Orqaga",
        "btn_cancel": "❌ Bekor qilish",
        "btn_share_phone": "📱 Telefon raqamini yuborish",
        "phone_invalid": "Iltimos, pastdagi tugma orqali telefon raqamingizni yuboring yoki uni qo‘lda kiriting.",
        "phone_must_be_self": "Iltimos, o‘z telefon raqamingizni yuboring.",
        "slot_taken": "⚠️ Afsuski, bu vaqt allaqachon band. Iltimos, boshqa vaqtni tanlang.",
        "choose_service": "Xizmatni tanlang:",
        "choose_master": "Ustani tanlang:",
        "choose_date": "Sanani tanlang:",
        "choose_time": "Vaqtni tanlang:",
        "enter_name": "Ismingizni kiriting:",
        "enter_phone": "Telefon raqamingizni kiriting:",
        "booking_success": "✅ Yozuv muvaffaqiyatli yaratildi!\n\nXizmat: <b>{service}</b>\nSana: {date}\nVaqt: {time}\nIsm: {name}\nTelefon: {phone}\n\nTasdiqlash uchun siz bilan bog‘lanamiz.",
        "booking_cancelled": "Yozuv bekor qilindi.",
        "price_list": "<b>{salon_name} narxlari:</b>\n\n{services}",
        "address": "📍 <b>Manzil:</b> {address}\n\n🕐 <b>Ish vaqti:</b> {work_hours}",
        "contacts": "📞 <b>Telefon:</b> {phone}\nTelegram: {telegram}",
    },
}


def salon_text(lang: str, key: str, **kwargs):
    lang = lang if lang in TEXTS else "ru"
    values = {
        "salon_name": SALON["name"],
        "description": SALON["description"],
        "address": SALON["address"],
        "phone": SALON["phone"],
        "telegram": SALON["telegram"],
        "work_hours": SALON["work_hours"],
        **kwargs,
    }
    return TEXTS[lang].get(key, key).format(**values)


def services_for(lang: str):
    lang = lang if lang in TEXTS else "ru"
    return {
        key: service[lang]
        for key, service in SALON["services"].items()
    }


def price_list_for(lang: str):
    lines = []
    for service in SALON["services"].values():
        lines.append(f"• {service[lang]} — {service['price']}")
    return "\n".join(lines)


# Оставляем короткий t() для совместимости со старыми обработчиками.
def t(lang: str, key: str, **kwargs):
    if key == "services":
        return services_for(lang)
    if key == "price_list":
        kwargs["services"] = price_list_for(lang)
    return salon_text(lang, key, **kwargs)
