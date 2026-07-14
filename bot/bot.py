"""
CH-SPA Telegram Bot — Receipt parsing + bonus redemption
Flow: /start → subscribe → phone → receipt URL → parse → more? → bonus table
"""
import os, json, re, time, threading
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
import httpx

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# ============================================
# CONFIG
# ============================================
BOT_TOKEN = os.getenv('BOT_TOKEN', '')
_admin_ids_str = os.getenv('ADMIN_USER_ID', '0')
ADMIN_IDS = set(int(x.strip()) for x in _admin_ids_str.split(',') if x.strip())
ADMIN_USER_ID = next(iter(ADMIN_IDS)) if ADMIN_IDS else 0  # first admin for legacy use
MANAGERS_GROUP_CHAT_ID = os.getenv('MANAGERS_GROUP_CHAT_ID', '')
TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ============================================
# DATABASE (SQLite)
# ============================================
from db import (
    init_db, now_iso,
    get_user, upsert_user, update_user, get_all_users,
    log_event, get_conversion_stats,
    kv_get, kv_set,
    create_receipt, get_receipt_by_number, get_user_receipts, burn_receipts,
    create_purchase, get_user_purchases, get_unburned_purchase_count,
    get_user_by_ref_code, ref_code_exists, resolve_referral_chain, kv_get_int,
    grant_bonus_to_user, get_granted_bonuses,
    remove_bonus_from_user, remove_all_bonuses_from_user
)
from receipt_parser import parse_receipt, matches_our_products

# ============================================
# TELEGRAM HTTP HELPERS
# ============================================
def tg(method: str, **params):
    http_timeout = params.pop('http_timeout', 30)
    last_err = None
    for attempt in range(3):
        try:
            r = httpx.post(f"{TG_API}/{method}", json=params, timeout=http_timeout)
            return r.json()
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            # Connection failed — safe to retry (request never reached server)
            last_err = e
            if attempt < 2:
                time.sleep(1)
        except Exception as e:
            # Timeout or other error — DON'T retry, request may already be processed
            raise
    raise last_err

# ============================================
# KEYBOARDS
# ============================================
def ikb(buttons):
    return json.dumps({"inline_keyboard": buttons})

def kb_subscribe():
    return ikb([[{"text": "Проверить подписку", "callback_data": "SUB_CONFIRMED"}]])

def kb_contact():
    return json.dumps({
        "keyboard": [[{"text": "Поделиться контактом", "request_contact": True}]],
        "resize_keyboard": True,
        "one_time_keyboard": True
    })

def kb_yes_no():
    return ikb([
        [{"text": "Да", "callback_data": "MORE_YES"},
         {"text": "Нет", "callback_data": "MORE_NO"}]
    ])

def kb_how_to_receipt():
    return ikb([[{"text": "Как получить чек?", "callback_data": "HOW_TO_RECEIPT"}]])

def kb_bonus_table(purchase_count: int):
    """Build bonus table with active/inactive buttons based on purchase count."""
    buttons = []
    for tier in BONUS_TIERS:
        required = tier['required_purchases']
        is_unlocked = purchase_count >= required
        label = f"{'✅' if is_unlocked else '🔒'} {tier['bonus_name']} (нужно {required} покуп.)"
        if is_unlocked:
            buttons.append([{"text": label, "callback_data": f"CLAIM_{tier['bonus_key']}"}])
        else:
            buttons.append([{"text": label, "callback_data": "BONUS_LOCKED"}])

    # "Buy more" button with store link
    buttons.append([{"text": "Купить ещё", "url": STORE_LINK}])
    # Back button
    buttons.append([{"text": "Назад", "callback_data": "BACK_TO_RECEIPTS"}])

    return ikb(buttons)

def kb_main_menu():
    return ikb([
        [{"text": "Мои покупки", "callback_data": "SHOW_PURCHASES"}],
        [{"text": "Получить бонусы", "callback_data": "SHOW_BONUSES"}],
    ])

def kb_back_only():
    return ikb([[{"text": "Назад", "callback_data": "BACK_TO_MAIN"}]])

def kb_admin_menu():
    return ikb([
        [{"text": "Пользователи", "callback_data": "ADMIN_USERS"}],
        [{"text": "Реферальный %", "callback_data": "ADMIN_REF_SETTINGS"}],
        [{"text": "Статистика", "callback_data": "ADMIN_STATS"}],
        [{"text": "Экспорт CSV", "callback_data": "ADMIN_EXPORT"}],
    ])

def kb_admin_reply():
    """Persistent reply keyboard for admins — always visible at bottom."""
    return json.dumps({
        "keyboard": [
            [{"text": "Пользователи"}, {"text": "Статистика"}],
            [{"text": "Реферальный %"}, {"text": "Экспорт"}],
            [{"text": "Скрыть меню"}],
        ],
        "resize_keyboard": True
    })

def kb_admin_back():
    return ikb([[{"text": "Назад", "callback_data": "ADMIN_MENU"}]])

def kb_admin_users_page(users_data, page, total_pages):
    """users_data: list of (tid, first_name, phone, ref_code, purchase_count)"""
    buttons = []
    for tid, first_name, phone, ref_code, pcount in users_data:
        label = f"{first_name or '—'} | {phone or '—'} | {ref_code or '—'} | {pcount} покуп."
        if len(label) > 64:
            label = label[:61] + '...'
        buttons.append([{"text": label, "callback_data": f"ADMIN_USER_{tid}"}])

    nav = []
    if page > 0:
        nav.append({"text": "пред.", "callback_data": f"ADMIN_USERS_PAGE_{page-1}"})
    if page < total_pages - 1:
        nav.append({"text": "след.", "callback_data": f"ADMIN_USERS_PAGE_{page+1}"})
    if nav:
        buttons.append(nav)
    buttons.append([{"text": "Назад", "callback_data": "ADMIN_MENU"}])
    return ikb(buttons)

def kb_admin_user_detail(user_tid):
    return ikb([
        [{"text": "Бонус 1", "callback_data": f"ADMIN_GRANT_B1_{user_tid}"},
         {"text": "Бонус 2", "callback_data": f"ADMIN_GRANT_B2_{user_tid}"},
         {"text": "Бонус 3", "callback_data": f"ADMIN_GRANT_B3_{user_tid}"}],
        [{"text": "Открыть ВСЕ бонусы", "callback_data": f"ADMIN_GRANT_ALL_{user_tid}"}],
        [{"text": "Закрыть ВСЕ бонусы", "callback_data": f"ADMIN_REVOKE_ALL_{user_tid}"}],
        [{"text": "Назад к списку", "callback_data": "ADMIN_USERS"}],
        [{"text": "В меню", "callback_data": "ADMIN_MENU"}],
    ])

def kb_admin_ref_settings():
    return ikb([
        [{"text": "Изменить L1 (прямой)", "callback_data": "ADMIN_REF_SET_L1"}],
        [{"text": "Изменить L2", "callback_data": "ADMIN_REF_SET_L2"}],
        [{"text": "Изменить L3", "callback_data": "ADMIN_REF_SET_L3"}],
        [{"text": "Назад", "callback_data": "ADMIN_MENU"}],
    ])

# ============================================
# CONSTANTS
# ============================================
BONUS_TIERS = [
    {
        'bonus_key': 'bonus_1',
        'bonus_name': 'Вводный урок',
        'description': 'Вводный урок онлайн-школы',
        'required_purchases': 1,
        'url': 'https://example.com/bonus1',
    },
    {
        'bonus_key': 'bonus_2',
        'bonus_name': 'Мини-курс',
        'description': 'Мини-курс по теме',
        'required_purchases': 3,
        'url': 'https://example.com/bonus2',
    },
    {
        'bonus_key': 'bonus_3',
        'bonus_name': 'Мастер-класс',
        'description': 'Мастер-класс с экспертом',
        'required_purchases': 5,
        'url': 'https://example.com/bonus3',
    },
]

STORE_LINK = 'https://www.wildberries.ru/seller/CHSPA'
RECEIPT_IMAGES_DIR = os.path.join(os.path.dirname(__file__), '..', 'чек', '1')
RECEIPT_STEPS = [
    "Зайдите в Wildberries и нажмите кнопку личного кабинета",
    "В личном кабинете нажмите на иконку аккаунта",
    "Нажмите <b>«Оплата»</b>",
    "Нажмите <b>«Чеки»</b>",
    "Выберите чек покупки в нашем магазине",
    "Нажмите кнопку <b>«Отправить»</b>",
    "Выберите <b>Telegram</b>",
    "В поиске найдите <b>@chspa_gifts_bot</b> («Подарки SPA») и нажмите «Отправить»"
]

# ============================================
# MESSAGE SENDERS
# ============================================
WELCOME_IMAGE = os.path.join(os.path.dirname(__file__), '..', '1we.png')

def send_message(chat_id, text, reply_markup=None, parse_mode=None):
    kwargs = {'chat_id': chat_id, 'text': text}
    if reply_markup:
        kwargs['reply_markup'] = reply_markup
    if parse_mode:
        kwargs['parse_mode'] = parse_mode
    return tg('sendMessage', **kwargs)

def send_photo(chat_id, photo_path_or_id, caption=None, reply_markup=None, parse_mode=None):
    data = {'chat_id': str(chat_id)}
    if caption:
        data['caption'] = caption
    if reply_markup:
        data['reply_markup'] = reply_markup
    if parse_mode:
        data['parse_mode'] = parse_mode
    url = f"{TG_API}/sendPhoto"
    is_file = os.path.isfile(str(photo_path_or_id))
    last_err = None
    for attempt in range(3):
        try:
            if is_file:
                with open(photo_path_or_id, 'rb') as f:
                    r = httpx.post(url, data=data, files={'photo': f}, timeout=45)
            else:
                data['photo'] = photo_path_or_id
                r = httpx.post(url, data=data, timeout=45)
            return r.json()
        except (httpx.ConnectError, httpx.ConnectTimeout) as e:
            last_err = e
            if attempt < 2:
                time.sleep(1)
        except Exception:
            raise
    raise last_err

def delete_message(chat_id, message_id):
    try:
        tg('deleteMessage', chat_id=chat_id, message_id=message_id, http_timeout=10)
    except Exception as e:
        print(f"deleteMessage error: {e}")

def answer_callback(cb_id, text=None):
    kwargs = {'callback_query_id': cb_id}
    if text:
        kwargs['text'] = text
    return tg('answerCallbackQuery', **kwargs)

# ============================================
# BOT CLASS
# ============================================
class Bot:
    def __init__(self):
        saved = kv_get('update_offset')
        self.offset = int(saved) if saved else 0
        self._seen = set()
        self._seen_callbacks = set()  # deduplicate callback queries
        self.user_data = {}  # tid -> {instruction_msg_ids: [...], ...}
        self.running = True

    def _ensure_user_data(self, tid):
        if tid not in self.user_data:
            self.user_data[tid] = {}

    def _delete_instruction_messages(self, tid):
        """Delete previously sent instruction messages for a user."""
        ud = self.user_data.get(tid, {})
        msg_ids = ud.get('instruction_msg_ids', [])
        for mid in msg_ids:
            delete_message(tid, mid)
        if msg_ids:
            self.user_data[tid]['instruction_msg_ids'] = []

    def process_update(self, update: dict):
        uid = update.get('update_id')
        if uid in self._seen:
            print(f"SKIP duplicate update_id={uid}")
            return
        self._seen.add(uid)
        try:
            msg = update.get('message', {})
            cb = update.get('callback_query', {})
            if msg:
                print(f"UPDATE {uid}: message from={msg.get('from',{}).get('id')} text={(msg.get('text','') or '(no text)')[:80]}")
            elif cb:
                print(f"UPDATE {uid}: callback from={cb.get('from',{}).get('id')} data={cb.get('data','')}")

            if 'message' in update:
                msg = update['message']
                user = msg.get('from', {})
                tid = user.get('id', 0)
                if not tid:
                    return

                text = msg.get('text', '')
                contact = msg.get('contact')

                if text.startswith('/start'):
                    self._handle_start(msg, tid, user)
                elif contact:
                    self._handle_contact(tid, contact)
                elif text:
                    self._handle_text(msg, tid, text)

            elif 'callback_query' in update:
                cb = update['callback_query']
                tid = cb.get('from', {}).get('id', 0)
                if not tid:
                    return
                self._handle_callback(cb, tid)

        except Exception as e:
            print(f"ERROR processing update: {e}")

    # ---- HANDLERS ----

    def _handle_start(self, msg, tid, user):
        first_name = user.get('first_name', '') or ''
        username = user.get('username', '') or ''
        last_name = user.get('last_name', '') or ''

        # Parse referral code from deep link: /start REF_CODE
        text = msg.get('text', '')
        ref_code = None
        parts = text.split()
        if len(parts) > 1:
            ref_code = parts[1]

        existing = get_user(tid)
        if existing:
            update_user(tid, {'last_seen': now_iso()})
            state = existing.get('user_state', 'new')
            has_phone = bool(existing.get('phone'))
            purchase_count = get_unburned_purchase_count(tid)
            granted = get_granted_bonuses(tid)

            # If bonuses were manually granted by admin, show them
            if granted:
                tier_names = {t['bonus_key']: t['bonus_name'] for t in BONUS_TIERS}
                lines = ['Вам открыты бонусы:']
                for bk in granted:
                    tier = next((t for t in BONUS_TIERS if t['bonus_key'] == bk), None)
                    if tier:
                        lines.append(f"• <b>{tier['bonus_name']}</b> — {tier['url']}")
                send_message(tid, '\n'.join(lines), parse_mode='HTML', reply_markup=kb_how_to_receipt())
                log_event(tid, 'start_resume_granted')
                return

            # Resume from saved state — skip already completed steps
            if has_phone:
                if purchase_count > 0:
                    self._show_bonuses(tid)
                else:
                    update_user(tid, {'user_state': 'awaiting_receipt', 'last_seen': now_iso()})
                    send_message(tid,
                        "С возвращением! Пришлите <b>ссылку на чек</b> из Wildberries.",
                        parse_mode='HTML',
                        reply_markup=kb_how_to_receipt()
                    )
                log_event(tid, 'start_resume')
                return

            if state == 'awaiting_contact':
                send_message(tid, "Поделитесь номером телефона чтобы продолжить.", kb_contact())
                log_event(tid, 'start_resume')
                return

            if state == 'awaiting_receipt':
                send_message(tid,
                    "Пришлите <b>ссылку на чек</b> из Wildberries.",
                    parse_mode='HTML',
                    reply_markup=kb_how_to_receipt()
                )
                log_event(tid, 'start_resume')
                return

            if state == 'asking_more_receipts':
                count = get_unburned_purchase_count(tid)
                send_message(tid,
                    f"У вас {count} активных покупок. Есть ещё чеки?",
                    reply_markup=kb_yes_no()
                )
                log_event(tid, 'start_resume')
                return

            if state == 'choosing_bonus':
                self._show_bonuses(tid)
                log_event(tid, 'start_resume')
                return

            update_user(tid, {'user_state': 'new', 'last_seen': now_iso()})
        else:
            # Generate unique referral code
            import secrets
            user_ref = secrets.token_hex(4).upper()  # 8-char code
            while ref_code_exists(user_ref):
                user_ref = secrets.token_hex(4).upper()

            # Resolve 3-level referral chain
            l1 = l2 = l3 = None
            if ref_code:
                l1, l2, l3 = resolve_referral_chain(ref_code)
                # Prevent self-referral
                if l1 == tid:
                    l1 = l2 = l3 = None
                if l2 == tid:
                    l2 = l3 = None
                if l3 == tid:
                    l3 = None

            upsert_user(tid, {
                'username': username,
                'first_name': first_name,
                'last_name': last_name,
                'user_state': 'new',
                'ref_code': user_ref,
                'referred_by': l1,
                'referred_by_l2': l2,
                'referred_by_l3': l3,
                'last_seen': now_iso()
            })
            update_user(tid, {'user_state': 'new', 'last_seen': now_iso()})

        # New user or reset — full flow from start
        log_event(tid, 'start')
        greeting = f"Приветствую Вас{f', {first_name}' if first_name else ''}!"
        text = (
            f"{greeting}\n\n"
            f"<b>CH-SPA</b> — место, где Ваши покупки превращаются в подарки.\n\n"
            f"Здесь Вы получаете вводные уроки, мини-курсы, чек-листы от лучших онлайн-школ — всё это уже ждёт Вас внутри.\n\n"
            f"Но и это ещё не всё: получите реальные деньги. Но об этом позже.\n\n"
            f"Для начала <b>ПОДПИШИТЕСЬ</b> на канал @SkrabVarezkaPiling и нажмите «Проверить подписку» — и начнём!"
        )
        send_photo(tid, WELCOME_IMAGE, caption=text, parse_mode='HTML', reply_markup=kb_subscribe())

    def _handle_contact(self, tid, contact):
        user = get_user(tid)
        if not user:
            send_message(tid, "Отправьте /start чтобы начать")
            return
        phone = contact.get('phone_number', '')
        update_user(tid, {'phone': phone, 'user_state': 'awaiting_receipt', 'last_seen': now_iso()})
        log_event(tid, 'contact_saved', {'phone': phone})

        # Remove contact keyboard
        remove_kb = json.dumps({"remove_keyboard": True})
        send_message(tid, "Телефон сохранён!", reply_markup=remove_kb)
        send_message(tid,
            "Теперь пришлите <b>ссылку на чек</b> из Wildberries.\n"
            "Если нужна инструкция, нажмите кнопку ниже.",
            parse_mode='HTML',
            reply_markup=kb_how_to_receipt()
        )

    def _handle_text(self, msg, tid, text):
        user = get_user(tid)
        if not user:
            send_message(tid, "Отправьте /start чтобы начать")
            return
        state = user.get('user_state', 'new')

        # Admin commands — highest priority
        if tid in ADMIN_IDS:
            if text in ('/admin', '/a'):
                self._show_admin_menu(tid)
                return
            if self.user_data.get(tid, {}).get('admin_state'):
                self._handle_admin_state_input(tid, text)
                return
            # Reply keyboard buttons
            if text == 'Пользователи':
                self._show_admin_users(tid, page=0)
                return
            if text == 'Статистика':
                self._show_admin_stats(tid)
                return
            if text == 'Реферальный %':
                self._show_admin_ref_settings(tid)
                return
            if text == 'Экспорт':
                self._show_admin_export(tid)
                return
            if text == 'Скрыть меню':
                send_message(tid, "Меню скрыто.", reply_markup=json.dumps({"remove_keyboard": True}))
                return

        # Receipt URL — any URL when in awaiting_receipt state
        if state == 'awaiting_receipt' and re.match(r'^https?://', text):
            self._process_receipt_url(tid, text)
            return

        # Manual receipt number/text in awaiting_receipt (fallback)
        if state == 'awaiting_receipt':
            self._process_receipt_text(tid, text)
            return

        # Commands
        if text in ('Мои покупки', '/purchases'):
            self._show_purchases(tid)
        elif text in ('Получить бонусы', '/bonuses'):
            self._show_bonuses(tid)
        elif text in ('Мой статус', '/status'):
            self._show_status(tid)
        elif text in ('Сбросить', 'Начать заново', '/reset'):
            update_user(tid, {'user_state': 'new', 'purchase_status': None, 'bonus_access': 'locked', 'selected_package': None, 'last_seen': now_iso()})
            log_event(tid, 'reset')
            send_message(tid, "Всё сброшено! Начните заново с /start")
        elif text in ('Помощь', '/help'):
            send_message(tid, "Чат-поддержка: @ch_spa_support\n\nКоманды:\n/start - начать\n/status - мой статус\n/purchases - мои покупки\n/bonuses - получить бонусы\n/help - помощь\n/reset - начать заново")
        elif text in ('Продолжить', '/continue'):
            send_message(tid, "Продолжаем! Используйте /bonuses чтобы посмотреть доступные бонусы.")
        elif text in ('Назад', '/back'):
            update_user(tid, {'user_state': 'new', 'last_seen': now_iso()})
            send_message(tid, "Главное меню.", reply_markup=kb_main_menu())

        # Legacy admin text commands
        elif tid in ADMIN_IDS:
            self._handle_admin(tid, text)

    def _process_receipt_url(self, tid, url):
        """Parse receipt URL via DeepSeek, save purchases, ask if more."""
        user = get_user(tid)
        if not user:
            return

        # Delete instruction messages to keep chat clean
        self._delete_instruction_messages(tid)

        send_message(tid, "Обрабатываю чек...")

        parsed = parse_receipt(url)

        if parsed.get('error'):
            log_event(tid, 'receipt_parse_error', {'url': url, 'error': parsed['error']})
            send_message(tid,
                f"Не удалось распознать чек автоматически.\n\n"
                f"Ошибка: {parsed['error']}\n\n"
                f"Пожалуйста, введите данные чека вручную:\n"
                f"— Номер чека\n"
                f"— Список товаров (название, количество)\n\n"
                f"Или попробуйте отправить другую ссылку.",
                reply_markup=kb_how_to_receipt()
            )
            return

        receipt_number = parsed.get('receipt_number')
        products = parsed.get('products', [])

        if not receipt_number:
            log_event(tid, 'receipt_no_number', {'url': url, 'parsed': parsed})
            send_message(tid,
                "Не удалось определить номер чека. Попробуйте ввести данные вручную или отправьте другую ссылку.",
                reply_markup=kb_how_to_receipt()
            )
            return

        # Anti-reuse check
        existing = get_receipt_by_number(receipt_number)
        if existing and existing['is_used']:
            log_event(tid, 'receipt_already_used', {'receipt_number': receipt_number})
            send_message(tid, "Данный чек уже использован и не может быть применён повторно.")
            return
        if existing:
            log_event(tid, 'receipt_duplicate', {'receipt_number': receipt_number})
            send_message(tid, "Этот чек уже был загружен ранее. Повторная загрузка не требуется.")
            return

        # Filter to our products
        our_items = [p for p in products if matches_our_products(p.get('name', ''))]

        # Save receipt
        receipt = create_receipt(tid, receipt_number, url, parsed)

        # Save purchases
        total_qty = 0
        for item in our_items:
            qty = item.get('quantity', 1) or 1
            price = item.get('price')
            create_purchase(tid, receipt['id'], item.get('name', 'неизвестно'), qty, price)
            total_qty += qty

        # Also save non-matching products comment
        if not our_items and products:
            # Products found but none match ours
            create_purchase(tid, receipt['id'], '(не наши товары)', 0, 0)

        log_event(tid, 'receipt_processed', {
            'receipt_number': receipt_number,
            'total_products': len(products),
            'our_products': len(our_items),
            'total_quantity': total_qty,
        })

        # Build response
        if our_items:
            lines = [f"• {p.get('name', 'товар')} — {p.get('quantity', 1)} шт." for p in our_items]
            msg = (
                f"Чек №{receipt_number} обработан.\n\n"
                f"Найдены наши товары:\n" + "\n".join(lines) + f"\n\n"
                f"Всего покупок: {total_qty} шт."
            )
        else:
            msg = (
                f"Чек №{receipt_number} обработан.\n\n"
                f"В чеке не найдено наших товаров (варежки).\n"
                f"Если это ошибка, отправьте данные чека вручную."
            )

        update_user(tid, {'user_state': 'asking_more_receipts', 'last_seen': now_iso()})
        send_message(tid, msg + "\n\nУ вас есть ещё чеки?", reply_markup=kb_yes_no())

    def _process_receipt_text(self, tid, text):
        """Handle manual receipt text input as fallback."""
        user = get_user(tid)
        if not user:
            return

        # Delete instruction messages
        self._delete_instruction_messages(tid)

        # Try to parse with DeepSeek
        from receipt_parser import parse_receipt_text
        parsed = parse_receipt_text(text)

        if parsed.get('error') or not parsed.get('receipt_number'):
            send_message(tid,
                "Не удалось распознать данные. Пожалуйста, пришлите ссылку на чек или введите в формате:\n\n"
                "Номер чека: ...\n"
                "Товары: варежки 2 шт.",
                reply_markup=kb_how_to_receipt()
            )
            return

        receipt_number = parsed.get('receipt_number')
        existing = get_receipt_by_number(receipt_number)
        if existing:
            if existing['is_used']:
                send_message(tid, "Данный чек уже использован.")
            else:
                send_message(tid, "Этот чек уже был загружен ранее.")
            return

        products = parsed.get('products', [])
        our_items = [p for p in products if matches_our_products(p.get('name', ''))]

        receipt = create_receipt(tid, receipt_number, None, parsed)
        total_qty = 0
        for item in our_items:
            qty = item.get('quantity', 1) or 1
            create_purchase(tid, receipt['id'], item.get('name', 'неизвестно'), qty, item.get('price'))
            total_qty += qty

        log_event(tid, 'receipt_processed_text', {'receipt_number': receipt_number, 'our_items': total_qty})

        update_user(tid, {'user_state': 'asking_more_receipts', 'last_seen': now_iso()})
        send_message(tid,
            f"Чек №{receipt_number} обработан. Найдено товаров: {total_qty} шт.\n\nУ вас есть ещё чеки?",
            reply_markup=kb_yes_no()
        )

    def _show_purchases(self, tid):
        """Show user's accumulated unburned purchases."""
        count = get_unburned_purchase_count(tid)
        purchases = get_user_purchases(tid, unburned_only=True)
        receipts = get_user_receipts(tid, unburned_only=True)

        if count == 0:
            send_message(tid,
                "У вас пока нет активных покупок.\n\n"
                "Отправьте чек из Wildberries, чтобы начать.",
                reply_markup=kb_how_to_receipt()
            )
            return

        lines = [f"Активных покупок: <b>{count}</b> шт.\n"]
        if purchases:
            lines.append("Товары:")
            for p in purchases[:20]:
                lines.append(f"• {p['product_name']} — {p['quantity']} шт.")
        if receipts:
            lines.append(f"\nЗагружено чеков: {len(receipts)}")

        lines.append("\nИспользуйте /bonuses чтобы получить подарки.")
        send_message(tid, "\n".join(lines), parse_mode='HTML', reply_markup=kb_how_to_receipt())

    def _show_bonuses(self, tid):
        """Show bonus table based on purchase count."""
        count = get_unburned_purchase_count(tid)
        update_user(tid, {'user_state': 'choosing_bonus', 'last_seen': now_iso()})

        if count == 0:
            send_message(tid,
                "У вас пока нет покупок для получения бонусов.\n\n"
                "Отправьте чек из Wildberries.",
                reply_markup=kb_how_to_receipt()
            )
            return

        lines = [f"У вас <b>{count}</b> покуп.\n"]
        lines.append("Доступные бонусы:")

        for tier in BONUS_TIERS:
            required = tier['required_purchases']
            unlocked = count >= required
            icon = "✅" if unlocked else "🔒"
            lines.append(f"{icon} <b>{tier['bonus_name']}</b> — нужно {required} покуп. ({tier['description']})")

        send_message(tid, "\n".join(lines), parse_mode='HTML', reply_markup=kb_bonus_table(count))

    def _show_status(self, tid):
        user = get_user(tid)
        if not user:
            return
        state_names = {
            'new': 'новый',
            'awaiting_subscription': 'ожидает подписки',
            'awaiting_contact': 'ожидает контакта',
            'awaiting_receipt': 'ожидает чека',
            'asking_more_receipts': 'ожидает ответа (ещё чеки?)',
            'choosing_bonus': 'выбор бонуса',
        }
        count = get_unburned_purchase_count(tid)
        s = user.get('user_state', 'неизвестно')
        msg = f"Статус: {state_names.get(s, s)}\nАктивных покупок: {count}\n"
        if user.get('phone'):
            msg += f"Телефон: {user['phone']}\n"
        send_message(tid, msg)

    def _claim_bonus(self, tid, bonus_key):
        """Claim a bonus: check purchase count, burn receipts, send bonus."""
        tier = next((t for t in BONUS_TIERS if t['bonus_key'] == bonus_key), None)
        if not tier:
            answer_callback(tid, "Бонус не найден")
            return

        required = tier['required_purchases']
        count = get_unburned_purchase_count(tid)

        if count < required:
            send_message(tid, f"Недостаточно покупок. Нужно {required}, у вас {count}.")
            return

        # Get unburned receipts, oldest first
        receipts = get_user_receipts(tid, unburned_only=True)
        purchases = get_user_purchases(tid, unburned_only=True)

        # Calculate total quantity and pick receipts to burn
        to_burn = []
        accumulated = 0
        for r in reversed(receipts):  # oldest first
            r_purchases = [p for p in purchases if p['receipt_id'] == r['id']]
            r_qty = sum(p['quantity'] for p in r_purchases)
            to_burn.append(r['id'])
            accumulated += r_qty
            if accumulated >= required:
                break

        # Burn the receipts
        burn_receipts(to_burn, bonus_key)
        log_event(tid, 'bonus_claimed', {
            'bonus_key': bonus_key,
            'receipts_burned': to_burn,
            'purchases_consumed': accumulated,
            'required': required,
        })

        bonus_url = tier.get('url', 'https://example.com/placeholder')

        remaining = get_unburned_purchase_count(tid)
        update_user(tid, {'user_state': 'new', 'last_seen': now_iso()})

        send_message(tid,
            f"Поздравляем! Вы получили <b>{tier['bonus_name']}</b>!\n\n"
            f"Ваш подарок доступен по ссылке:\n{bonus_url}\n\n"
            f"Использовано покупок: {required}\n"
            f"Осталось покупок: {remaining}\n\n"
            f"Продолжайте копить покупки для новых подарков!",
            parse_mode='HTML',
            reply_markup=kb_main_menu()
        )

        # Notify managers
        try:
            send_message(MANAGERS_GROUP_CHAT_ID,
                f"Пользователь {tid} забрал бонус «{tier['bonus_name']}»\n"
                f"Сожжено чеков: {len(to_burn)}\n"
                f"Осталось покупок: {remaining}"
            )
        except:
            pass

    # ---- CALLBACK HANDLER ----

    def _handle_callback(self, cb, tid):
        cb_id = cb.get('id', '')
        data = cb.get('data', '')

        # Deduplicate — Telegram may re-deliver callback queries
        if cb_id in self._seen_callbacks:
            print(f"SKIP duplicate callback cb_id={cb_id}")
            answer_callback(cb_id)
            return
        self._seen_callbacks.add(cb_id)

        answer_callback(cb_id)

        user = get_user(tid)
        if not user:
            send_message(tid, "Ошибка: пользователь не найден. Отправьте /start")
            return

        # Idempotent guard for state transitions
        current_state = user.get('user_state', 'new')

        # Subscription confirmation
        if data == 'SUB_CONFIRMED':
            if current_state == 'awaiting_contact':
                return  # already processed
            print(f"CALLBACK SUB_CONFIRMED tid={tid}")
            check = tg('getChatMember', chat_id='@SkrabVarezkaPiling', user_id=tid)
            status = check.get('result', {}).get('status', '')
            print(f"SUB_CONFIRMED status={status}")
            if status in ('creator', 'administrator', 'member'):
                log_event(tid, 'subscription_confirmed')
                # If user already shared phone, skip to receipt
                if user.get('phone'):
                    update_user(tid, {'user_state': 'awaiting_receipt', 'last_seen': now_iso()})
                    send_message(tid,
                        "Подписка подтверждена! Пришлите <b>ссылку на чек</b> из Wildberries.",
                        parse_mode='HTML',
                        reply_markup=kb_how_to_receipt()
                    )
                else:
                    update_user(tid, {'user_state': 'awaiting_contact', 'last_seen': now_iso()})
                    send_message(tid, "Отлично! Теперь поделитесь номером телефона чтобы продолжить.", kb_contact())
            else:
                answer_callback(cb_id, "Вы не подписаны на @SkrabVarezkaPiling!")
                send_message(tid,
                    "Вы не подписаны на канал @SkrabVarezkaPiling.\n\nПодпишитесь и нажмите кнопку снова.",
                    kb_subscribe()
                )

        # More receipts: Yes
        elif data == 'MORE_YES':
            update_user(tid, {'user_state': 'awaiting_receipt', 'last_seen': now_iso()})
            send_message(tid,
                "Пришлите следующий чек (ссылку).",
                reply_markup=kb_how_to_receipt()
            )

        # More receipts: No → show bonuses
        elif data == 'MORE_NO':
            self._show_bonuses(tid)

        # Claim bonus
        elif data.startswith('CLAIM_'):
            bonus_key = data.replace('CLAIM_', '')
            self._claim_bonus(tid, bonus_key)

        # Locked bonus clicked
        elif data == 'BONUS_LOCKED':
            count = get_unburned_purchase_count(tid)
            answer_callback(cb_id, f"Недостаточно покупок. У вас {count}, нужно больше.")
            send_message(tid,
                f"Этот бонус пока недоступен. У вас {count} покуп.\n"
                f"Купите ещё варежки в нашем магазине и пришлите новый чек!",
                reply_markup=ikb([[{"text": "Купить ещё", "url": STORE_LINK}]])
            )

        # Back from bonus selection
        elif data == 'BACK_TO_RECEIPTS':
            update_user(tid, {'user_state': 'asking_more_receipts', 'last_seen': now_iso()})
            send_message(tid, "У вас есть ещё чеки?", reply_markup=kb_yes_no())

        # Back to main
        elif data == 'BACK_TO_MAIN':
            update_user(tid, {'user_state': 'new', 'last_seen': now_iso()})
            send_message(tid, "Главное меню.", reply_markup=kb_main_menu())

        # Show purchases
        elif data == 'SHOW_PURCHASES':
            self._show_purchases(tid)

        # Show bonuses
        elif data == 'SHOW_BONUSES':
            self._show_bonuses(tid)

        # Admin callbacks
        elif data.startswith('ADMIN_'):
            self._handle_admin_callback(tid, data)

        # Receipt instruction with screenshots
        elif data == 'HOW_TO_RECEIPT':
            self._send_receipt_instruction(tid)

    # ---- INSTRUCTION ----

    def _send_receipt_instruction(self, tid):
        """Send step-by-step receipt instructions with screenshots.
        Track message IDs so they can be deleted when receipt arrives."""
        self._ensure_user_data(tid)
        if 'instruction_msg_ids' not in self.user_data[tid]:
            self.user_data[tid]['instruction_msg_ids'] = []

        r = send_message(tid, "<b>Как получить чек из Wildberries:</b>", parse_mode='HTML')
        if r.get('ok') and r['result'].get('message_id'):
            self.user_data[tid]['instruction_msg_ids'].append(r['result']['message_id'])

        for i, step in enumerate(RECEIPT_STEPS):
            img_path = os.path.join(RECEIPT_IMAGES_DIR, f"{i+1}.jpg")
            caption = f"<b>Шаг {i+1}.</b> {step}"
            try:
                r = send_photo(tid, img_path, caption=caption, parse_mode='HTML')
                if r.get('ok') and r['result'].get('message_id'):
                    self.user_data[tid]['instruction_msg_ids'].append(r['result']['message_id'])
            except Exception as e:
                print(f"Failed to send step {i+1} image: {e}")
                r = send_message(tid, f"<b>Шаг {i+1}.</b> {step}", parse_mode='HTML')
                if r.get('ok') and r['result'].get('message_id'):
                    self.user_data[tid]['instruction_msg_ids'].append(r['result']['message_id'])

    # ---- ADMIN ----

    def _handle_admin(self, tid, text):
        if text == '/stats':
            stats = get_conversion_stats()
            reply = "Статистика:\n"
            period_names = {'today': 'Сегодня', 'week': 'За 7 дней'}
            field_names = {
                'starts': 'Стартов', 'contacts': 'Контактов', 'packages': 'Выбрано пакетов',
                'submissions': 'Заявок', 'approved': 'Одобрено', 'bonus_clicks': 'Кликов по бонусам',
                'reviews': 'Отзывов', 'payments': 'Платежей', 'active_users': 'Активных пользователей'
            }
            for period, s in stats.items():
                reply += f"\n{period_names.get(period, period)}:\n"
                for k, v in s.items():
                    reply += f"  {field_names.get(k, k)}: {v}\n"
            send_message(tid, reply)

        elif text.startswith('/broadcast'):
            msg_text = text.replace('/broadcast ', '').strip()
            users = get_all_users()
            send_message(tid, f"Рассылка на {len(users)} пользователей.")
            for u in users:
                try:
                    send_message(u['telegram_id'], msg_text)
                except:
                    pass

        elif text.startswith('/user'):
            uid = text.replace('/user ', '').strip()
            u = get_user(int(uid))
            if u:
                send_message(tid, f"Пользователь:\n{json.dumps(u, ensure_ascii=False, indent=2, default=str)}")
            else:
                send_message(tid, "Не найден.")

        elif text == '/export_users':
            users = get_all_users()
            csv = "telegram_id,username,phone,user_state,bonus_access\n"
            csv += "\n".join(
                f"{u.get('telegram_id','')},{u.get('username','')},{u.get('phone','')},{u.get('user_state','')},{u.get('bonus_access','')}"
                for u in users
            )
            send_message(tid, f"Экспорт:\n\n{csv[:3800]}")

    # ---- ADMIN PANEL ----

    def _admin_send(self, tid, text, reply_markup=None):
        """Send admin message, hiding keyboard of the previous admin message first."""
        self._ensure_user_data(tid)
        prev = self.user_data[tid].get('admin_msg')
        if prev:
            try:
                tg('editMessageReplyMarkup', chat_id=tid, message_id=prev['msg_id'],
                   reply_markup=json.dumps({"inline_keyboard": []}), http_timeout=10)
            except Exception:
                pass
        r = send_message(tid, text, reply_markup=reply_markup)
        if r.get('ok') and r['result'].get('message_id'):
            self.user_data[tid]['admin_msg'] = {'msg_id': r['result']['message_id']}

    def _show_admin_menu(self, tid):
        # Send inline menu
        self._admin_send(tid, "Админ-панель", reply_markup=kb_admin_menu())
        # Show persistent reply keyboard
        send_message(tid, "Кнопки админа внизу", reply_markup=kb_admin_reply())

    def _handle_admin_callback(self, tid, data):
        if data == 'ADMIN_MENU':
            self._show_admin_menu(tid)

        elif data == 'ADMIN_USERS':
            self._show_admin_users(tid, page=0)

        elif data.startswith('ADMIN_USERS_PAGE_'):
            page = int(data.split('_')[-1])
            self._show_admin_users(tid, page)

        elif data.startswith('ADMIN_USER_'):
            user_tid = int(data.replace('ADMIN_USER_', ''))
            self._show_admin_user_detail(tid, user_tid)

        elif data == 'ADMIN_REF_SETTINGS':
            self._show_admin_ref_settings(tid)

        elif data == 'ADMIN_REF_SET_L1':
            self.user_data[tid] = self.user_data.get(tid, {})
            self.user_data[tid]['admin_state'] = 'admin_setting_ref_l1'
            self._admin_send(tid, "Введите новый процент для уровня 1 (прямой реферал) — только число:")

        elif data == 'ADMIN_REF_SET_L2':
            self.user_data[tid] = self.user_data.get(tid, {})
            self.user_data[tid]['admin_state'] = 'admin_setting_ref_l2'
            self._admin_send(tid, "Введите новый процент для уровня 2 — только число:")

        elif data == 'ADMIN_REF_SET_L3':
            self.user_data[tid] = self.user_data.get(tid, {})
            self.user_data[tid]['admin_state'] = 'admin_setting_ref_l3'
            self._admin_send(tid, "Введите новый процент для уровня 3 — только число:")

        elif data.startswith('ADMIN_GRANT_'):
            # Format: ADMIN_GRANT_B1/B2/B3/ALL_userid
            parts = data.split('_')
            grant_key = parts[2]  # B1, B2, B3, or ALL
            user_tid = int(parts[3])
            self._admin_grant_bonus(tid, user_tid, grant_key)

        elif data.startswith('ADMIN_REVOKE_'):
            # Format: ADMIN_REVOKE_B1/B2/B3/ALL_userid
            parts = data.split('_')
            revoke_key = parts[2]  # B1, B2, B3, or ALL
            user_tid = int(parts[3])
            self._admin_revoke_bonus(tid, user_tid, revoke_key)

        elif data == 'ADMIN_STATS':
            self._show_admin_stats(tid)

        elif data == 'ADMIN_EXPORT':
            self._show_admin_export(tid)

    def _show_admin_stats(self, tid):
        stats = get_conversion_stats()
        reply = "Статистика:\n"
        period_names = {'today': 'Сегодня', 'week': 'За 7 дней'}
        field_names = {
            'starts': 'Стартов', 'contacts': 'Контактов', 'packages': 'Выбрано пакетов',
            'submissions': 'Заявок', 'approved': 'Одобрено', 'bonus_clicks': 'Кликов по бонусам',
            'reviews': 'Отзывов', 'payments': 'Платежей', 'active_users': 'Активных пользователей'
        }
        for period, s in stats.items():
            reply += f"\n{period_names.get(period, period)}:\n"
            for k, v in s.items():
                reply += f"  {field_names.get(k, k)}: {v}\n"
        self._admin_send(tid, reply, reply_markup=kb_admin_back())

    def _show_admin_ref_settings(self, tid):
        l1 = kv_get_int('ref_commission_l1', 10)
        l2 = kv_get_int('ref_commission_l2', 5)
        l3 = kv_get_int('ref_commission_l3', 3)
        self._admin_send(tid,
            f"Реферальные комиссии:\n\n"
            f"Уровень 1 (прямой): {l1}%\n"
            f"Уровень 2: {l2}%\n"
            f"Уровень 3: {l3}%\n\n"
            f"Нажмите кнопку чтобы изменить:",
            reply_markup=kb_admin_ref_settings()
        )

    def _show_admin_export(self, tid):
        users = get_all_users()
        csv = "telegram_id,username,phone,first_name,user_state,ref_code,referred_by,referred_by_l2,referred_by_l3,created_at\n"
        csv += "\n".join(
            f"{u.get('telegram_id','')},{u.get('username','')},{u.get('phone','')},{u.get('first_name','')},{u.get('user_state','')},{u.get('ref_code','')},{u.get('referred_by','')},{u.get('referred_by_l2','')},{u.get('referred_by_l3','')},{u.get('created_at','')}"
            for u in users
        )
        self._admin_send(tid, f"Экспорт ({len(users)} пользователей):\n\n{csv[:3900]}", reply_markup=kb_admin_back())

    def _show_admin_users(self, tid, page=0):
        users = get_all_users()
        per_page = 5
        total_pages = max(1, (len(users) + per_page - 1) // per_page)
        page = max(0, min(page, total_pages - 1))
        start = page * per_page
        chunk = users[start:start + per_page]

        users_data = []
        for u in chunk:
            utid = u['telegram_id']
            pcount = get_unburned_purchase_count(utid)
            users_data.append((utid, u.get('first_name'), u.get('phone'), u.get('ref_code'), pcount))

        self._admin_send(tid,
            f"Пользователи (стр. {page+1}/{total_pages}, всего {len(users)}):",
            reply_markup=kb_admin_users_page(users_data, page, total_pages)
        )

    def _show_admin_user_detail(self, admin_tid, user_tid):
        u = get_user(user_tid)
        if not u:
            self._admin_send(admin_tid, "Пользователь не найден.", reply_markup=kb_admin_back())
            return

        purchases = get_user_purchases(user_tid, unburned_only=False)
        receipts = get_user_receipts(user_tid, unburned_only=False)
        unburned = get_unburned_purchase_count(user_tid)
        granted = get_granted_bonuses(user_tid)
        tier_names = {t['bonus_key']: t['bonus_name'] for t in BONUS_TIERS}

        # Referral info
        referrer = get_user(u['referred_by']) if u.get('referred_by') else None
        ref_l2 = get_user(u.get('referred_by_l2')) if u.get('referred_by_l2') else None
        ref_l3 = get_user(u.get('referred_by_l3')) if u.get('referred_by_l3') else None

        granted_line = ', '.join(tier_names.get(b, b) for b in granted) if granted else '—'

        text = (
            f"Пользователь #{user_tid}\n\n"
            f"Имя: {u.get('first_name', '—')} {u.get('last_name', '—')}\n"
            f"Username: @{u.get('username', '—')}\n"
            f"Телефон: {u.get('phone', '—')}\n"
            f"Статус: {u.get('user_state', '—')}\n"
            f"Выданы бонусы: {granted_line}\n"
            f"Реф. код: {u.get('ref_code', '—')}\n"
            f"Создан: {u.get('created_at', '—')[:19]}\n\n"
            f"--- Покупки ---\n"
            f"Всего покупок: {sum(p['quantity'] for p in purchases)}\n"
            f"Не сожжено: {unburned}\n"
            f"Чеков загружено: {len(receipts)}\n"
            f"Сожжено чеков: {sum(1 for r in receipts if r['is_used'])}\n\n"
            f"--- Рефералы ---\n"
            f"L1 (пригласил): {referrer['first_name'] if referrer else '—'} ({u.get('referred_by', '—')})\n"
            f"L2: {ref_l2['first_name'] if ref_l2 else '—'} ({u.get('referred_by_l2', '—')})\n"
            f"L3: {ref_l3['first_name'] if ref_l3 else '—'} ({u.get('referred_by_l3', '—')})\n"
        )
        self._admin_send(admin_tid, text, reply_markup=kb_admin_user_detail(user_tid))

    def _admin_grant_bonus(self, admin_tid, user_tid, grant_key):
        """Grant bonus access to a user manually."""
        bonus_map = {'B1': 'bonus_1', 'B2': 'bonus_2', 'B3': 'bonus_3'}
        user = get_user(user_tid)
        if not user:
            self._admin_send(admin_tid, "Пользователь не найден.", reply_markup=kb_admin_back())
            return

        if grant_key == 'ALL':
            for bk in ['bonus_1', 'bonus_2', 'bonus_3']:
                grant_bonus_to_user(user_tid, bk)
            granted = {'bonus_1', 'bonus_2', 'bonus_3'}
        else:
            bk = bonus_map.get(grant_key)
            if not bk:
                self._admin_send(admin_tid, f"Неизвестный бонус: {grant_key}")
                return
            grant_bonus_to_user(user_tid, bk)
            granted = get_granted_bonuses(user_tid)

        tier_names = {t['bonus_key']: t['bonus_name'] for t in BONUS_TIERS}
        granted_names = [tier_names.get(b, b) for b in granted]

        log_event(user_tid, 'bonus_granted_by_admin', {'by': admin_tid, 'grant_key': grant_key, 'granted': list(granted)})

        # Notify admin
        self._admin_send(admin_tid,
            f"Пользователю #{user_tid} ({user.get('first_name', '—')}) открыты бонусы:\n"
            + '\n'.join(f"• {n}" for n in granted_names),
            reply_markup=kb_admin_back()
        )

        # Send bonuses to user
        for bk in (granted if grant_key == 'ALL' else [bonus_map[grant_key]]):
            tier = next((t for t in BONUS_TIERS if t['bonus_key'] == bk), None)
            if tier:
                try:
                    send_message(user_tid,
                        f"Администратор открыл для вас бонус: <b>{tier['bonus_name']}</b>\n\n"
                        f"Ссылка: {tier['url']}",
                        parse_mode='HTML'
                    )
                except Exception as e:
                    print(f"Failed to notify user {user_tid}: {e}")

    def _admin_revoke_bonus(self, admin_tid, user_tid, revoke_key):
        """Revoke bonus access from a user manually."""
        bonus_map = {'B1': 'bonus_1', 'B2': 'bonus_2', 'B3': 'bonus_3'}
        user = get_user(user_tid)
        if not user:
            self._admin_send(admin_tid, "Пользователь не найден.", reply_markup=kb_admin_back())
            return

        if revoke_key == 'ALL':
            remove_all_bonuses_from_user(user_tid)
            removed_names = ['Бонус 1', 'Бонус 2', 'Бонус 3']
        else:
            bk = bonus_map.get(revoke_key)
            if not bk:
                self._admin_send(admin_tid, f"Неизвестный бонус: {revoke_key}")
                return
            remove_bonus_from_user(user_tid, bk)
            tier_names = {t['bonus_key']: t['bonus_name'] for t in BONUS_TIERS}
            removed_names = [tier_names.get(bk, bk)]

        log_event(user_tid, 'bonus_revoked_by_admin', {'by': admin_tid, 'revoke_key': revoke_key})

        self._admin_send(admin_tid,
            f"У пользователя #{user_tid} ({user.get('first_name', '—')}) закрыты бонусы:\n"
            + '\n'.join(f"• {n}" for n in removed_names),
            reply_markup=kb_admin_back()
        )

        # Notify user
        try:
            send_message(user_tid,
                "Администратор отозвал ваши бонусы. Используйте /start чтобы увидеть актуальное состояние.",
            )
        except Exception as e:
            print(f"Failed to notify user {user_tid}: {e}")

    def _handle_admin_state_input(self, tid, text):
        state = self.user_data.get(tid, {}).get('admin_state', '')
        if state.startswith('admin_setting_ref_'):
            level = state.replace('admin_setting_ref_', '')  # l1, l2, or l3
            level_names = {'l1': '1 (прямой)', 'l2': '2', 'l3': '3'}
            if not text.isdigit():
                self._admin_send(tid, "Пожалуйста, введите число. Попробуйте снова:")
                return
            value = int(text)
            if value < 0 or value > 100:
                self._admin_send(tid, "Процент должен быть от 0 до 100. Попробуйте снова:")
                return
            key = f'ref_commission_{level}'
            kv_set(key, str(value))
            self.user_data[tid]['admin_state'] = None
            self._admin_send(tid, f"Комиссия уровня {level_names.get(level, level)} установлена: {value}%")
            # Show updated settings
            l1 = kv_get_int('ref_commission_l1', 10)
            l2 = kv_get_int('ref_commission_l2', 5)
            l3 = kv_get_int('ref_commission_l3', 3)
            self._admin_send(tid,
                f"Текущие комиссии:\n"
                f"Уровень 1: {l1}%\n"
                f"Уровень 2: {l2}%\n"
                f"Уровень 3: {l3}%",
                reply_markup=kb_admin_ref_settings()
            )
        else:
            self.user_data[tid]['admin_state'] = None
            self._admin_send(tid, "Неизвестное действие.", reply_markup=kb_admin_menu())


# ============================================
# MAIN
# ============================================
def main():
    print("Init database...")
    init_db()

    bot = Bot()

    print("Bot started. Polling for updates...")

    while bot.running:
        try:
            result = tg('getUpdates', offset=bot.offset, timeout=10, limit=10, http_timeout=15)
            if result.get('ok') and result.get('result'):
                updates = result['result']
                print(f"GOT {len(updates)} updates, ids: {[u['update_id'] for u in updates]}")
                for update in updates:
                    bot.process_update(update)
                    bot.offset = max(bot.offset, update['update_id'] + 1)
                kv_set('update_offset', str(bot.offset))
                print(f"Offset now: {bot.offset}")
        except Exception as e:
            print(f"Polling error: {e}")
            time.sleep(5)


if __name__ == '__main__':
    main()
