"""
SQLite database layer — replaces Supabase REST API.
All functions are synchronous for simplicity.
"""
import sqlite3, json, os, threading
from datetime import datetime, timezone

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'chspa.db')

_local = threading.local()

def _conn():
    """Thread-local connection. Auto-creates on first access."""
    if not hasattr(_local, 'conn') or _local.conn is None:
        _local.conn = sqlite3.connect(DB_PATH)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn

def now_iso():
    return datetime.now(timezone.utc).isoformat()

# ============================================
# SCHEMA
# ============================================
SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id     INTEGER NOT NULL UNIQUE,
    username        TEXT,
    phone           TEXT,
    first_name      TEXT,
    last_name       TEXT,
    user_state      TEXT NOT NULL DEFAULT 'new',
    selected_package TEXT,
    bonus_access    TEXT NOT NULL DEFAULT 'locked',
    purchase_status TEXT DEFAULT NULL,
    last_seen       TEXT DEFAULT NULL,
    last_followup_at TEXT,
    created_at      TEXT DEFAULT NULL,
    ref_code        TEXT UNIQUE,
    referred_by     INTEGER REFERENCES users(telegram_id),
    referred_by_l2  INTEGER REFERENCES users(telegram_id),
    referred_by_l3  INTEGER REFERENCES users(telegram_id),
    granted_bonuses TEXT DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_users_telegram ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_users_state ON users(user_state);

CREATE TABLE IF NOT EXISTS submissions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(telegram_id),
    package         TEXT NOT NULL,
    photo_file_id   TEXT NOT NULL,
    photo_tg_url    TEXT,
    purchase_status TEXT NOT NULL DEFAULT 'pending',
    timer_started_at TEXT DEFAULT NULL,
    approved_at     TEXT,
    decided_by      INTEGER,
    decided_at      TEXT,
    reject_reason   TEXT,
    created_at      TEXT DEFAULT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_submissions_one_pending
    ON submissions(user_id, purchase_status) WHERE purchase_status = 'pending';

CREATE INDEX IF NOT EXISTS idx_submissions_user ON submissions(user_id);
CREATE INDEX IF NOT EXISTS idx_submissions_status ON submissions(purchase_status);

CREATE TABLE IF NOT EXISTS review_submissions (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id                   INTEGER NOT NULL REFERENCES users(telegram_id),
    marketplace               TEXT NOT NULL,
    review_screenshot_file_id TEXT NOT NULL,
    product_photo_file_id     TEXT NOT NULL,
    status                    TEXT NOT NULL DEFAULT 'pending',
    decided_by                INTEGER,
    decided_at                TEXT,
    created_at                TEXT DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_review_user ON review_submissions(user_id);
CREATE INDEX IF NOT EXISTS idx_review_status ON review_submissions(status);

CREATE TABLE IF NOT EXISTS bonuses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    package     TEXT NOT NULL,
    bonus_key   TEXT NOT NULL,
    bonus_name  TEXT NOT NULL,
    school_name TEXT,
    real_url    TEXT NOT NULL,
    description TEXT,
    is_active   INTEGER DEFAULT 1,
    created_at  TEXT DEFAULT NULL,
    UNIQUE(package, bonus_key)
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    event_name  TEXT NOT NULL,
    payload     TEXT DEFAULT '{}',
    created_at  TEXT DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_user ON events(user_id);
CREATE INDEX IF NOT EXISTS idx_events_name ON events(event_name);
CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);

CREATE TABLE IF NOT EXISTS kv_store (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payments (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL REFERENCES users(telegram_id),
    provider            TEXT NOT NULL DEFAULT 'yookassa',
    provider_payment_id TEXT,
    amount              REAL NOT NULL,
    currency            TEXT NOT NULL DEFAULT 'RUB',
    status              TEXT NOT NULL DEFAULT 'pending',
    idempotency_key     TEXT NOT NULL UNIQUE,
    payload             TEXT DEFAULT '{}',
    created_at          TEXT DEFAULT NULL,
    updated_at          TEXT DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_payments_user ON payments(user_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(status);

CREATE TABLE IF NOT EXISTS broadcasts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    sent_by         INTEGER NOT NULL,
    message_text    TEXT NOT NULL,
    segment_filter  TEXT DEFAULT '{}',
    recipient_count INTEGER DEFAULT 0,
    delivered_count INTEGER DEFAULT 0,
    created_at      TEXT DEFAULT NULL
);

CREATE TABLE IF NOT EXISTS receipts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(telegram_id),
    receipt_number  TEXT NOT NULL,
    receipt_url     TEXT,
    parsed_data     TEXT DEFAULT '{}',
    is_used         INTEGER DEFAULT 0,
    used_for_bonus  TEXT,
    used_at         TEXT,
    created_at      TEXT DEFAULT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_receipts_number ON receipts(receipt_number);
CREATE INDEX IF NOT EXISTS idx_receipts_user ON receipts(user_id);

CREATE TABLE IF NOT EXISTS purchases (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             INTEGER NOT NULL REFERENCES users(telegram_id),
    receipt_id          INTEGER NOT NULL REFERENCES receipts(id),
    product_name        TEXT NOT NULL,
    quantity            INTEGER DEFAULT 1,
    price               REAL,
    is_burned           INTEGER DEFAULT 0,
    burned_for_bonus    TEXT,
    burned_at           TEXT,
    created_at          TEXT DEFAULT NULL
);

CREATE INDEX IF NOT EXISTS idx_purchases_user ON purchases(user_id);
CREATE INDEX IF NOT EXISTS idx_purchases_receipt ON purchases(receipt_id);
CREATE INDEX IF NOT EXISTS idx_purchases_burned ON purchases(is_burned);
"""

def init_db():
    """Create tables and seed data if needed."""
    conn = _conn()
    conn.executescript(SCHEMA)
    conn.commit()

    # Migrate existing databases: add referral columns if missing
    for col in ['referred_by_l2', 'referred_by_l3', 'granted_bonuses']:
        try:
            conn.execute(f"ALTER TABLE users ADD COLUMN {col} INTEGER REFERENCES users(telegram_id)")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists

    # Seed bonuses if empty
    count = conn.execute("SELECT COUNT(*) FROM bonuses").fetchone()[0]
    if count == 0:
        seed_bonuses = [
            ('standard', 'bonus_1', 'Вводный урок', '', 'https://example.com/placeholder', 'Вводный урок онлайн-школы'),
            ('standard', 'bonus_2', 'Мини-курс', '', 'https://example.com/placeholder', 'Мини-курс по теме'),
            ('standard', 'bonus_3', 'Чек-лист', '', 'https://example.com/placeholder', 'Полезный чек-лист'),
            ('premium',  'bonus_1', 'Вводный урок', '', 'https://example.com/placeholder', 'Вводный урок онлайн-школы'),
            ('premium',  'bonus_2', 'Мини-курс', '', 'https://example.com/placeholder', 'Мини-курс по теме'),
            ('premium',  'bonus_3', 'Мастер-класс', '', 'https://example.com/placeholder', 'Мастер-класс с экспертом'),
            ('vip',      'bonus_1', 'Вводный урок', '', 'https://example.com/placeholder', 'Вводный урок онлайн-школы'),
            ('vip',      'bonus_2', 'Мини-курс', '', 'https://example.com/placeholder', 'Мини-курс по теме'),
            ('vip',      'bonus_3', 'Полный курс', '', 'https://example.com/placeholder', 'Полный доступ к курсу'),
        ]
        conn.executemany(
            "INSERT OR IGNORE INTO bonuses (package, bonus_key, bonus_name, school_name, real_url, description) VALUES (?,?,?,?,?,?)",
            seed_bonuses
        )
        conn.commit()

# ============================================
# QUERY HELPERS (replaces sb_get / sb_patch / sb_post)
# ============================================
def _row_to_dict(row):
    if row is None:
        return None
    return dict(row)

def _rows_to_dicts(rows):
    return [dict(r) for r in rows]

# -- users --
def get_user(telegram_id: int):
    row = _conn().execute("SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone()
    return _row_to_dict(row)

def upsert_user(telegram_id: int, data: dict):
    """Insert or update user. data keys must match column names."""
    existing = get_user(telegram_id)
    conn = _conn()
    if existing:
        if not data:
            return existing
        columns = ', '.join(f"{k} = ?" for k in data)
        values = list(data.values()) + [telegram_id]
        conn.execute(f"UPDATE users SET {columns} WHERE telegram_id = ?", values)
    else:
        data['telegram_id'] = telegram_id
        if 'created_at' not in data:
            data['created_at'] = now_iso()
        if 'user_state' not in data:
            data['user_state'] = 'new'
        if 'bonus_access' not in data:
            data['bonus_access'] = 'locked'
        columns = ', '.join(data.keys())
        placeholders = ', '.join('?' * len(data))
        conn.execute(f"INSERT INTO users ({columns}) VALUES ({placeholders})", list(data.values()))
    conn.commit()
    return get_user(telegram_id)

def update_user(telegram_id: int, data: dict):
    """Partial update. Returns updated row."""
    conn = _conn()
    columns = ', '.join(f"{k} = ?" for k in data)
    values = list(data.values()) + [telegram_id]
    conn.execute(f"UPDATE users SET {columns} WHERE telegram_id = ?", values)
    conn.commit()
    return get_user(telegram_id)

def get_all_users():
    return _rows_to_dicts(_conn().execute("SELECT * FROM users").fetchall())

def get_user_by_ref_code(ref_code: str):
    return _row_to_dict(_conn().execute("SELECT * FROM users WHERE ref_code = ?", (ref_code,)).fetchone())

def ref_code_exists(ref_code: str) -> bool:
    return _conn().execute("SELECT 1 FROM users WHERE ref_code = ?", (ref_code,)).fetchone() is not None

def grant_bonus_to_user(telegram_id: int, bonus_key: str):
    """Add a bonus to user's granted bonuses (comma-separated)."""
    user = _row_to_dict(_conn().execute("SELECT granted_bonuses FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone())
    if not user:
        return
    current = user.get('granted_bonuses') or ''
    existing = set(b for b in current.split(',') if b)
    existing.add(bonus_key)
    new_val = ','.join(sorted(existing))
    _conn().execute("UPDATE users SET granted_bonuses = ? WHERE telegram_id = ?", (new_val, telegram_id))
    _conn().commit()

def remove_bonus_from_user(telegram_id: int, bonus_key: str):
    """Remove a bonus from user's granted bonuses."""
    user = _row_to_dict(_conn().execute("SELECT granted_bonuses FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone())
    if not user:
        return
    current = user.get('granted_bonuses') or ''
    existing = set(b for b in current.split(',') if b)
    existing.discard(bonus_key)
    new_val = ','.join(sorted(existing)) if existing else None
    _conn().execute("UPDATE users SET granted_bonuses = ? WHERE telegram_id = ?", (new_val, telegram_id))
    _conn().commit()

def remove_all_bonuses_from_user(telegram_id: int):
    """Remove all bonuses from user."""
    _conn().execute("UPDATE users SET granted_bonuses = NULL WHERE telegram_id = ?", (telegram_id,))
    _conn().commit()

def get_granted_bonuses(telegram_id: int) -> set:
    """Get set of granted bonus keys for user."""
    user = _row_to_dict(_conn().execute("SELECT granted_bonuses FROM users WHERE telegram_id = ?", (telegram_id,)).fetchone())
    if not user or not user.get('granted_bonuses'):
        return set()
    return set(b for b in user['granted_bonuses'].split(',') if b)

def resolve_referral_chain(ref_code: str) -> tuple:
    """Resolve 3-level referral chain from a ref_code.
    Returns (l1_id, l2_id, l3_id) — telegram_id or None for each level."""
    l1 = _conn().execute("SELECT telegram_id, referred_by FROM users WHERE ref_code = ?", (ref_code,)).fetchone()
    if not l1:
        return (None, None, None)

    l1_id = l1['telegram_id']
    l2_id = l1['referred_by']
    l3_id = None
    if l2_id:
        l2_row = _conn().execute("SELECT referred_by FROM users WHERE telegram_id = ?", (l2_id,)).fetchone()
        if l2_row:
            l3_id = l2_row['referred_by']

    return (l1_id, l2_id, l3_id)

# -- submissions --
def create_submission(user_id: int, package: str, photo_file_id: str):
    conn = _conn()
    cur = conn.execute(
        "INSERT INTO submissions (user_id, package, photo_file_id, purchase_status, timer_started_at, created_at) VALUES (?,?,?,'pending',?,?)",
        (user_id, package, photo_file_id, now_iso(), now_iso())
    )
    conn.commit()
    return _row_to_dict(conn.execute("SELECT * FROM submissions WHERE id = ?", (cur.lastrowid,)).fetchone())

def get_pending_submission(user_id: int):
    return _row_to_dict(_conn().execute(
        "SELECT * FROM submissions WHERE user_id = ? AND purchase_status = 'pending'", (user_id,)
    ).fetchone())

def get_submission(sub_id: int):
    return _row_to_dict(_conn().execute("SELECT * FROM submissions WHERE id = ?", (sub_id,)).fetchone())

def update_submission(sub_id: int, data: dict):
    conn = _conn()
    columns = ', '.join(f"{k} = ?" for k in data)
    values = list(data.values()) + [sub_id]
    conn.execute(f"UPDATE submissions SET {columns} WHERE id = ?", values)
    conn.commit()

def get_pending_submissions_older_than(cutoff_iso: str):
    return _rows_to_dicts(_conn().execute(
        "SELECT * FROM submissions WHERE purchase_status = 'pending' AND timer_started_at <= ?", (cutoff_iso,)
    ).fetchall())

# -- review_submissions --
def create_review(user_id: int, marketplace: str, screenshot_id: str, product_photo_id: str):
    conn = _conn()
    cur = conn.execute(
        "INSERT INTO review_submissions (user_id, marketplace, review_screenshot_file_id, product_photo_file_id, status, created_at) VALUES (?,?,?,?,'pending',?)",
        (user_id, marketplace, screenshot_id, product_photo_id, now_iso())
    )
    conn.commit()
    return _row_to_dict(conn.execute("SELECT * FROM review_submissions WHERE id = ?", (cur.lastrowid,)).fetchone())

def get_review(rev_id: int):
    return _row_to_dict(_conn().execute("SELECT * FROM review_submissions WHERE id = ?", (rev_id,)).fetchone())

def update_review(rev_id: int, data: dict):
    conn = _conn()
    columns = ', '.join(f"{k} = ?" for k in data)
    values = list(data.values()) + [rev_id]
    conn.execute(f"UPDATE review_submissions SET {columns} WHERE id = ?", values)
    conn.commit()

# -- bonuses --
def get_bonuses(package: str):
    return _rows_to_dicts(_conn().execute(
        "SELECT * FROM bonuses WHERE package = ? AND is_active = 1", (package,)
    ).fetchall())

# -- events --
def log_event(user_id: int, event_name: str, payload: dict = None):
    _conn().execute(
        "INSERT INTO events (user_id, event_name, payload, created_at) VALUES (?,?,?,?)",
        (user_id, event_name, json.dumps(payload or {}, ensure_ascii=False), now_iso())
    )
    _conn().commit()

# -- stats --
def get_conversion_stats():
    conn = _conn()
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    week_start = (datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                  .replace(day=datetime.now(timezone.utc).day - 7)).isoformat()

    def count(event_name, since):
        return conn.execute(
            "SELECT COUNT(*) FROM events WHERE event_name = ? AND created_at >= ?",
            (event_name, since)
        ).fetchone()[0]

    def active_users(since):
        return conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM events WHERE created_at >= ?",
            (since,)
        ).fetchone()[0]

    today_start = today + 'T00:00:00'
    return {
        'today': {
            'starts': count('start', today_start),
            'contacts': count('contact_saved', today_start),
            'packages': count('package_selected', today_start),
            'submissions': count('submission_created', today_start),
            'approved': count('submission_approved', today_start),
            'bonus_clicks': count('bonus_clicked', today_start),
            'reviews': count('review_approved', today_start),
            'payments': count('payment_succeeded', today_start),
            'active_users': active_users(today_start),
        },
        'week': {
            'starts': count('start', week_start),
            'contacts': count('contact_saved', week_start),
            'packages': count('package_selected', week_start),
            'submissions': count('submission_created', week_start),
            'approved': count('submission_approved', week_start),
            'bonus_clicks': count('bonus_clicked', week_start),
            'reviews': count('review_approved', week_start),
            'payments': count('payment_succeeded', week_start),
            'active_users': active_users(week_start),
        }
    }

# ============================================
# KEY-VALUE STORE (persistent offset, etc.)
# ============================================
def kv_get(key: str, default=None):
    row = _conn().execute("SELECT value FROM kv_store WHERE key = ?", (key,)).fetchone()
    return row['value'] if row else default

def kv_get_int(key: str, default=0):
    """Read int from kv_store. Returns default if key missing or not a valid int."""
    val = kv_get(key)
    if val is None:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default

def kv_set(key: str, value: str):
    _conn().execute("INSERT OR REPLACE INTO kv_store (key, value) VALUES (?,?)", (key, value))
    _conn().commit()

# -- receipts --
def create_receipt(user_id: int, receipt_number: str, receipt_url: str = None, parsed_data: dict = None):
    conn = _conn()
    cur = conn.execute(
        "INSERT INTO receipts (user_id, receipt_number, receipt_url, parsed_data, created_at) VALUES (?,?,?,?,?)",
        (user_id, receipt_number, receipt_url, json.dumps(parsed_data or {}, ensure_ascii=False), now_iso())
    )
    conn.commit()
    return _row_to_dict(conn.execute("SELECT * FROM receipts WHERE id = ?", (cur.lastrowid,)).fetchone())

def get_receipt_by_number(receipt_number: str):
    return _row_to_dict(_conn().execute(
        "SELECT * FROM receipts WHERE receipt_number = ?", (receipt_number,)
    ).fetchone())

def get_user_receipts(user_id: int, unburned_only: bool = True):
    if unburned_only:
        return _rows_to_dicts(_conn().execute(
            "SELECT * FROM receipts WHERE user_id = ? AND is_used = 0 ORDER BY created_at DESC",
            (user_id,)
        ).fetchall())
    return _rows_to_dicts(_conn().execute(
        "SELECT * FROM receipts WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
    ).fetchall())

def burn_receipts(receipt_ids: list, bonus_key: str):
    """Mark receipts as used for a bonus claim."""
    conn = _conn()
    now = now_iso()
    for rid in receipt_ids:
        conn.execute(
            "UPDATE receipts SET is_used = 1, used_for_bonus = ?, used_at = ? WHERE id = ?",
            (bonus_key, now, rid)
        )
        conn.execute(
            "UPDATE purchases SET is_burned = 1, burned_for_bonus = ?, burned_at = ? WHERE receipt_id = ?",
            (bonus_key, now, rid)
        )
    conn.commit()

# -- purchases --
def create_purchase(user_id: int, receipt_id: int, product_name: str, quantity: int = 1, price: float = None):
    conn = _conn()
    cur = conn.execute(
        "INSERT INTO purchases (user_id, receipt_id, product_name, quantity, price, created_at) VALUES (?,?,?,?,?,?)",
        (user_id, receipt_id, product_name, quantity, price, now_iso())
    )
    conn.commit()
    return _row_to_dict(conn.execute("SELECT * FROM purchases WHERE id = ?", (cur.lastrowid,)).fetchone())

def get_user_purchases(user_id: int, unburned_only: bool = True):
    if unburned_only:
        return _rows_to_dicts(_conn().execute(
            "SELECT * FROM purchases WHERE user_id = ? AND is_burned = 0 ORDER BY created_at DESC",
            (user_id,)
        ).fetchall())
    return _rows_to_dicts(_conn().execute(
        "SELECT * FROM purchases WHERE user_id = ? ORDER BY created_at DESC", (user_id,)
    ).fetchall())

def get_unburned_purchase_count(user_id: int) -> int:
    return _conn().execute(
        "SELECT COALESCE(SUM(quantity), 0) FROM purchases WHERE user_id = ? AND is_burned = 0",
        (user_id,)
    ).fetchone()[0]
