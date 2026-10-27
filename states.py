from aiogram.fsm.state import State, StatesGroup


class AdminSG(StatesGroup):
    # Спонсоры — ввод API-ключа
    service_key = State()

    # Приветка
    greeting_text = State()
    greeting_media = State()
    greeting_button = State()     # "текст - ссылка"

    # Промокоды
    promo_code = State()
    promo_amount = State()
    promo_limit = State()

    # Реклама
    ad_owner = State()            # @username / ID
    ad_name = State()
    ad_price = State()

    # Рассылка
    bc_text = State()
    bc_media = State()
    bc_button = State()
    bc_count = State()

    # Автопост
    ap_text = State()
    ap_media = State()
    ap_button = State()

    # Настройки
    setting_value = State()

    # Юзер — поиск
    user_search = State()
    
    user_balance = State()
    bc_button = State()
