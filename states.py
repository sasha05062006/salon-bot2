from aiogram.fsm.state import State, StatesGroup


class BookingStates(StatesGroup):
    choosing_language = State()
    waiting_for_service = State()
    waiting_for_master = State()
    waiting_for_date = State()
    waiting_for_time = State()
    waiting_for_name = State()
    waiting_for_phone = State()


class AdminStates(StatesGroup):
    adding_service_ru = State()
    adding_service_uz = State()
    adding_service_price = State()
    adding_service_duration = State()
    adding_service_confirm = State()
    adding_master_ru = State()
    adding_master_uz = State()
    adding_master_confirm = State()
    setup_name = State()
    setup_description = State()
    setup_address = State()
    setup_phone = State()
    setup_instagram = State()
    setup_telegram = State()
    bot_name = State()
    bot_description = State()
    bot_photo = State()
    editing_service_ru = State()
    editing_service_uz = State()
    editing_service_price = State()
    editing_service_duration = State()
