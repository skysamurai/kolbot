"""
Обработчик подтверждения телефона для бота.
Интегрируется в существующий bot.py.

Два сценария:

1. Mini App → бот (Telegram уже привязан через initData):
   - Mini App открывает tg://resolve?domain=<bot>&start=confirm_phone
   - Бот запрашивает контакт → сохраняет телефон

2. Браузер → бот (Email-пользователь привязывает Telegram):
   - Webapp показывает код и deep-link: t.me/<bot>?start=link_<CODE>
   - Бот привязывает Telegram к аккаунту по коду
   - Бот запрашивает контакт → сохраняет телефон
"""

import os
import httpx
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN       = os.getenv("BOT_TOKEN")
WEBAPP_API_URL  = os.getenv("WEBAPP_API_URL", "http://localhost:3000")
INTERNAL_SECRET = os.getenv("INTERNAL_SECRET")

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"


def tg(method: str, **params):
    r = httpx.post(f"{TG_API}/{method}", json=params, timeout=30)
    return r.json()


def request_contact(chat_id: int, text: str) -> dict:
    keyboard = {
        "keyboard": [[
            {"text": "Поделиться номером телефона", "request_contact": True}
        ]],
        "resize_keyboard": True,
        "one_time_keyboard": True,
    }
    return tg("sendMessage", chat_id=chat_id, text=text, reply_markup=keyboard)


def api_confirm_phone(telegram_id: int, phone: str) -> bool:
    """Сохраняет телефон через веб-сервер."""
    try:
        r = httpx.post(
            f"{WEBAPP_API_URL}/auth/confirm-phone",
            json={"telegram_id": telegram_id, "phone": phone, "secret": INTERNAL_SECRET},
            timeout=15,
        )
        return r.status_code == 200
    except Exception as e:
        print(f"[bot] confirm-phone error: {e}")
        return False


def api_link_by_code(code: str, telegram_id: int) -> dict | None:
    """Привязывает Telegram к email-аккаунту по коду."""
    try:
        r = httpx.post(
            f"{WEBAPP_API_URL}/auth/link-by-code",
            json={"code": code, "telegram_id": telegram_id, "secret": INTERNAL_SECRET},
            timeout=15,
        )
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        print(f"[bot] link-by-code error: {e}")
        return None


# ════════════════════════════════════════════════════════════
# ТОЧКИ ВХОДА ДЛЯ ИНТЕГРАЦИИ В bot.py
# ════════════════════════════════════════════════════════════

def handle_start_deeplink(text: str, chat_id: int, user_id: int) -> bool:
    """
    Обрабатывает deep-link в /start.
    Вызывать когда text начинается с '/start'.

    Возвращает True если это наш диплинк (не продолжать обычную обработку).
    """
    if not text:
        return False

    payload = text.replace("/start", "").strip()

    # ── Сценарий 1: привязка Telegram по коду (из браузера) ──
    if payload.startswith("link_"):
        code = payload.replace("link_", "").strip()
        if not code:
            tg("sendMessage", chat_id=chat_id, text="Неверный код привязки.")
            return True

        result = api_link_by_code(code, user_id)

        if result:
            tg("sendMessage", chat_id=chat_id,
               text="Telegram привязан к вашему аккаунту!")
            request_contact(chat_id,
                text="Теперь подтвердите номер телефона.\nНажмите кнопку ниже.")
        else:
            tg("sendMessage", chat_id=chat_id,
               text="Код не найден или истёк. "
                    "Запросите новый код в веб-приложении и попробуйте снова.")
        return True

    # ── Сценарий 2: подтверждение телефона (из Mini App) ──
    if payload == "confirm_phone":
        request_contact(chat_id,
            text="Для завершения регистрации подтвердите ваш номер телефона.\n\n"
                 "Нажмите кнопку ниже, чтобы поделиться контактом.")
        return True

    return False


def handle_contact(msg: dict) -> bool:
    """
    Обрабатывает сообщение с контактом (request_contact).
    Вызывать когда msg содержит 'contact'.

    Возвращает True если контакт обработан.
    """
    contact = msg.get("contact")
    if not contact:
        return False

    user_id = msg["from"]["id"]
    phone   = contact.get("phone_number", "")
    chat_id = msg["chat"]["id"]

    if not phone:
        tg("sendMessage", chat_id=chat_id,
           text="Не удалось получить номер. Попробуйте ещё раз.")
        return True

    success = api_confirm_phone(telegram_id=user_id, phone=phone)

    if success:
        tg("sendMessage", chat_id=chat_id,
           text="Номер телефона подтверждён!\n\n"
                "Возвращайтесь в приложение — статус обновится автоматически.",
           reply_markup={"remove_keyboard": True})
    else:
        tg("sendMessage", chat_id=chat_id,
           text="Ошибка при сохранении номера.\n"
                "Возможно, ваш Telegram ещё не привязан к аккаунту.\n"
                "Откройте веб-приложение и следуйте инструкциям.")

    return True


# ════════════════════════════════════════════════════════════
# ПРИМЕР ИНТЕГРАЦИИ В bot.py
# ════════════════════════════════════════════════════════════
#
# from bot_phone_handler import handle_start_deeplink, handle_contact
#
# def process_message(msg):
#     text    = msg.get("text", "")
#     chat_id = msg["chat"]["id"]
#     user_id = msg["from"]["id"]
#
#     # 1. Deep-link /start
#     if text.startswith("/start"):
#         if handle_start_deeplink(text, chat_id, user_id):
#             return
#         # ... обычная обработка /start ...
#
#     # 2. Контакт
#     if msg.get("contact"):
#         if handle_contact(msg):
#             return
#
#     # ... остальная логика ...
