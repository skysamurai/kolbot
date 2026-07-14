"""
Мульти-авторизация с ОБЯЗАТЕЛЬНЫМ Telegram и подтверждением телефона.
- Внутри Telegram: initData → проверка телефона → редирект в бота для шаринга контакта
- В браузере: email/Google → ПОТОМ обязательная привязка Telegram + подтверждение телефона
"""

import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timezone, timedelta

import bcrypt
import jwt
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import httpx
import sqlite3

load_dotenv()

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

INDEX_PATH = os.path.join(os.path.dirname(__file__), "index.html")

@app.get("/")
async def root():
    return FileResponse(INDEX_PATH)

# ── Config ──────────────────────────────────────────────
BOT_TOKEN    = os.getenv("BOT_TOKEN", "123456:abc")
BOT_USERNAME = os.getenv("BOT_USERNAME", "YourBot")  # без @
JWT_SECRET   = os.getenv("JWT_SECRET", secrets.token_hex(32))
JWT_TTL      = timedelta(days=30)
INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", secrets.token_hex(16))  # для бота

GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI  = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:3000/auth/google/callback")

TG_API = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ── DB ───────────────────────────────────────────────────
def get_db():
    db = sqlite3.connect("auth_example.db")
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db

def init_db():
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS accounts (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            email           TEXT UNIQUE,
            password        TEXT,
            google_id       TEXT UNIQUE,
            telegram_id     INTEGER UNIQUE,
            name            TEXT,
            phone           TEXT,
            phone_confirmed INTEGER NOT NULL DEFAULT 0,
            created_at      TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS sessions (
            token      TEXT PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES accounts(id),
            expires_at TEXT NOT NULL
        );
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS link_codes (
            code       TEXT PRIMARY KEY,
            account_id INTEGER NOT NULL REFERENCES accounts(id),
            expires_at TEXT NOT NULL,
            used       INTEGER NOT NULL DEFAULT 0
        )
    """)
    # миграция для существующей БД
    try:
        db.execute("ALTER TABLE accounts ADD COLUMN phone TEXT")
    except sqlite3.OperationalError:
        pass
    try:
        db.execute("ALTER TABLE accounts ADD COLUMN phone_confirmed INTEGER NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    db.commit()
    db.close()

init_db()

# ── Helpers ──────────────────────────────────────────────
def hash_pw(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()

def check_pw(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())

def make_jwt(account_id: int) -> str:
    payload = {"sub": str(account_id), "exp": datetime.now(timezone.utc) + JWT_TTL}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")

def verify_jwt(token: str) -> int:
    payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    return int(payload["sub"])

def account_json(acc) -> dict:
    return {
        "id": acc["id"], "name": acc["name"], "email": acc["email"],
        "telegram_id": acc["telegram_id"], "google_id": acc["google_id"],
        "phone": acc["phone"], "phone_confirmed": bool(acc["phone_confirmed"]),
        "can_proceed": bool(acc["telegram_id"] and acc["phone_confirmed"]),
    }

# ── Telegram initData валидация ──────────────────────────
def validate_telegram_init_data(init_data: str) -> dict:
    parsed = {}
    for part in init_data.split("&"):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        parsed[k] = v

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise ValueError("Missing hash in initData")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))

    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise ValueError("Invalid Telegram hash")

    auth_date = int(parsed.get("auth_date", 0))
    if datetime.now(timezone.utc).timestamp() - auth_date > 86400:
        raise ValueError("initData expired (> 24h)")

    return parsed

# ── Models ───────────────────────────────────────────────
class TelegramAuthRequest(BaseModel):
    init_data: str

class EmailRegisterRequest(BaseModel):
    email: str
    password: str
    name: str

class EmailLoginRequest(BaseModel):
    email: str
    password: str

class LinkTelegramRequest(BaseModel):
    init_data: str

class ConfirmPhoneRequest(BaseModel):
    """Вызывается ботом с internal_secret."""
    telegram_id: int
    phone: str
    secret: str

class LinkByCodeRequest(BaseModel):
    """Привязка Telegram к аккаунту через одноразовый код."""
    code: str
    telegram_id: int
    secret: str

# ── Endpoints ────────────────────────────────────────────

# ── Telegram Auth ────────────────────────────────────────
@app.post("/auth/telegram")
async def auth_telegram(body: TelegramAuthRequest):
    """Вход через Telegram Mini App. Возвращает флаг phone_confirmed."""
    try:
        tg_data = validate_telegram_init_data(body.init_data)
    except ValueError as e:
        raise HTTPException(401, detail=str(e))

    tg_user_raw = json.loads(tg_data["user"])
    tg_id   = tg_user_raw["id"]
    tg_name = tg_user_raw.get("first_name", "") + " " + tg_user_raw.get("last_name", "")
    tg_name = tg_name.strip() or tg_user_raw.get("username", "")

    db = get_db()
    acc = db.execute("SELECT * FROM accounts WHERE telegram_id = ?", (tg_id,)).fetchone()

    if acc is None:
        db.execute(
            "INSERT INTO accounts (telegram_id, name) VALUES (?, ?)",
            (tg_id, tg_name)
        )
        db.commit()
        acc = db.execute("SELECT * FROM accounts WHERE telegram_id = ?", (tg_id,)).fetchone()

    token = make_jwt(acc["id"])
    db.execute(
        "INSERT OR REPLACE INTO sessions (token, account_id, expires_at) VALUES (?, ?, ?)",
        (token, acc["id"], (datetime.now(timezone.utc) + JWT_TTL).isoformat())
    )
    db.commit()
    db.close()

    return {
        "token": token,
        "account": account_json(acc),
        # Если телефон не подтверждён — фронтенд покажет экран подтверждения
        "need_phone": not acc["phone_confirmed"],
        "bot_username": BOT_USERNAME,
    }

# ── Email Auth ───────────────────────────────────────────
@app.post("/auth/register")
async def register(body: EmailRegisterRequest):
    """Регистрация по email. Потом потребуется привязка Telegram + телефон."""
    if len(body.password) < 6:
        raise HTTPException(400, detail="Пароль минимум 6 символов")

    db = get_db()
    existing = db.execute("SELECT id FROM accounts WHERE email = ?", (body.email,)).fetchone()
    if existing:
        db.close()
        raise HTTPException(409, detail="Email уже занят")

    db.execute(
        "INSERT INTO accounts (email, password, name) VALUES (?, ?, ?)",
        (body.email, hash_pw(body.password), body.name)
    )
    db.commit()
    acc = db.execute("SELECT * FROM accounts WHERE email = ?", (body.email,)).fetchone()

    token = make_jwt(acc["id"])
    db.execute(
        "INSERT OR REPLACE INTO sessions (token, account_id, expires_at) VALUES (?, ?, ?)",
        (token, acc["id"], (datetime.now(timezone.utc) + JWT_TTL).isoformat())
    )
    db.commit()
    db.close()

    return {
        "token": token,
        "account": account_json(acc),
        "need_phone": True,
        "bot_username": BOT_USERNAME,
    }

@app.post("/auth/login")
async def login(body: EmailLoginRequest):
    """Вход по email/паролю."""
    db = get_db()
    acc = db.execute("SELECT * FROM accounts WHERE email = ?", (body.email,)).fetchone()
    if not acc or not check_pw(body.password, acc["password"]):
        db.close()
        raise HTTPException(401, detail="Неверный email или пароль")

    token = make_jwt(acc["id"])
    db.execute(
        "INSERT OR REPLACE INTO sessions (token, account_id, expires_at) VALUES (?, ?, ?)",
        (token, acc["id"], (datetime.now(timezone.utc) + JWT_TTL).isoformat())
    )
    db.commit()
    db.close()

    return {
        "token": token,
        "account": account_json(acc),
        "need_phone": not acc["phone_confirmed"],
        "bot_username": BOT_USERNAME,
    }

# ── Google OAuth ─────────────────────────────────────────
@app.get("/auth/google/login")
async def google_login():
    params = {
        "client_id":     GOOGLE_CLIENT_ID,
        "redirect_uri":  GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope":         "openid email profile",
        "access_type":   "offline",
        "prompt":        "consent",
    }
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return JSONResponse({"url": f"https://accounts.google.com/o/oauth2/v2/auth?{qs}"})

@app.get("/auth/google/callback")
async def google_callback(code: str):
    async with httpx.AsyncClient() as http:
        token_r = await http.post("https://oauth2.googleapis.com/token", data={
            "client_id":     GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri":  GOOGLE_REDIRECT_URI,
            "grant_type":    "authorization_code",
            "code":          code,
        })
    if token_r.status_code != 200:
        raise HTTPException(400, detail=f"Google token exchange failed: {token_r.text}")

    id_token = token_r.json().get("id_token")
    if not id_token:
        raise HTTPException(400, detail="No id_token from Google")

    payload = jwt.decode(id_token, options={"verify_signature": False})
    google_id = payload["sub"]
    email     = payload.get("email", "")
    name      = payload.get("name", email.split("@")[0])

    db = get_db()
    acc = db.execute("SELECT * FROM accounts WHERE google_id = ?", (google_id,)).fetchone()
    if acc is None:
        acc_by_email = db.execute("SELECT * FROM accounts WHERE email = ?", (email,)).fetchone()
        if acc_by_email:
            db.execute("UPDATE accounts SET google_id = ? WHERE id = ?", (google_id, acc_by_email["id"]))
            acc = db.execute("SELECT * FROM accounts WHERE id = ?", (acc_by_email["id"],)).fetchone()
        else:
            db.execute(
                "INSERT INTO accounts (email, google_id, name) VALUES (?, ?, ?)",
                (email, google_id, name)
            )
            db.commit()
            acc = db.execute("SELECT * FROM accounts WHERE google_id = ?", (google_id,)).fetchone()

    token = make_jwt(acc["id"])
    db.execute(
        "INSERT OR REPLACE INTO sessions (token, account_id, expires_at) VALUES (?, ?, ?)",
        (token, acc["id"], (datetime.now(timezone.utc) + JWT_TTL).isoformat())
    )
    db.commit()
    db.close()

    return {
        "token": token,
        "account": account_json(acc),
        "need_phone": not acc["phone_confirmed"],
        "bot_username": BOT_USERNAME,
    }

# ── Привязка Telegram (для браузерных пользователей) ─────
@app.post("/auth/link-telegram")
async def link_telegram(body: LinkTelegramRequest, request: Request):
    """Привязывает Telegram к существующему email/Google аккаунту."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(401, detail="Требуется JWT токен")

    try:
        account_id = verify_jwt(auth_header[7:])
    except jwt.PyJWTError:
        raise HTTPException(401, detail="Невалидный JWT")

    try:
        tg_data = validate_telegram_init_data(body.init_data)
    except ValueError as e:
        raise HTTPException(401, detail=str(e))

    tg_user_raw = json.loads(tg_data["user"])
    tg_id = tg_user_raw["id"]

    db = get_db()
    conflict = db.execute(
        "SELECT id FROM accounts WHERE telegram_id = ? AND id != ?", (tg_id, account_id)
    ).fetchone()
    if conflict:
        db.close()
        raise HTTPException(409, detail="Этот Telegram уже привязан к другому аккаунту")

    db.execute("UPDATE accounts SET telegram_id = ? WHERE id = ?", (tg_id, account_id))
    db.commit()
    db.close()

    return {"status": "ok", "telegram_id": tg_id}

# ── Подтверждение телефона (вызывается ботом) ────────────
@app.post("/auth/confirm-phone")
async def confirm_phone(body: ConfirmPhoneRequest):
    """Бот вызывает этот endpoint после получения контакта от пользователя."""
    if body.secret != INTERNAL_SECRET:
        raise HTTPException(403, detail="Неверный internal secret")

    db = get_db()
    acc = db.execute("SELECT * FROM accounts WHERE telegram_id = ?", (body.telegram_id,)).fetchone()
    if not acc:
        db.close()
        raise HTTPException(404, detail="Аккаунт с таким telegram_id не найден")

    db.execute(
        "UPDATE accounts SET phone = ?, phone_confirmed = 1 WHERE telegram_id = ?",
        (body.phone, body.telegram_id)
    )
    db.commit()
    db.close()

    return {"status": "ok", "telegram_id": body.telegram_id, "phone": body.phone}

# ── Генерация кода привязки Telegram ────────────────────
@app.post("/auth/generate-link-code")
async def generate_link_code(request: Request):
    """Генерирует одноразовый 6-значный код для привязки Telegram к email-аккаунту."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(401, detail="Нет токена")
    try:
        account_id = verify_jwt(auth_header[7:])
    except jwt.PyJWTError:
        raise HTTPException(401, detail="Токен невалиден")

    import random
    code = ''.join(random.choices('0123456789', k=6))

    db = get_db()
    # Удаляем старые неиспользованные коды этого аккаунта
    db.execute("DELETE FROM link_codes WHERE account_id = ? AND used = 0", (account_id,))
    db.execute(
        "INSERT INTO link_codes (code, account_id, expires_at) VALUES (?, ?, ?)",
        (code, account_id, (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat())
    )
    db.commit()
    db.close()

    return {"code": code, "bot_username": BOT_USERNAME, "expires_in_sec": 600}

# ── Привязка по коду (вызывается ботом) ──────────────────
@app.post("/auth/link-by-code")
async def link_by_code(body: LinkByCodeRequest):
    """Бот вызывает этот endpoint, когда пользователь отправляет код привязки."""
    if body.secret != INTERNAL_SECRET:
        raise HTTPException(403, detail="Неверный internal secret")

    db = get_db()
    link = db.execute(
        "SELECT * FROM link_codes WHERE code = ? AND used = 0 AND expires_at > ?",
        (body.code, datetime.now(timezone.utc).isoformat())
    ).fetchone()

    if not link:
        db.close()
        raise HTTPException(404, detail="Код не найден или истёк")

    # Проверяем, не привязан ли этот telegram_id к другому аккаунту
    conflict = db.execute(
        "SELECT id FROM accounts WHERE telegram_id = ? AND id != ?",
        (body.telegram_id, link["account_id"])
    ).fetchone()
    if conflict:
        db.close()
        raise HTTPException(409, detail="Этот Telegram уже привязан к другому аккаунту")

    db.execute("UPDATE accounts SET telegram_id = ? WHERE id = ?", (body.telegram_id, link["account_id"]))
    db.execute("UPDATE link_codes SET used = 1 WHERE code = ?", (body.code,))
    db.commit()
    db.close()

    return {"status": "ok", "account_id": link["account_id"], "telegram_id": body.telegram_id}

# ── Проверка сессии ──────────────────────────────────────
@app.get("/me")
async def me(request: Request):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(401, detail="Нет токена")

    try:
        account_id = verify_jwt(auth_header[7:])
    except jwt.PyJWTError:
        raise HTTPException(401, detail="Токен истёк или невалиден")

    db = get_db()
    acc = db.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
    db.close()

    if not acc:
        raise HTTPException(404, detail="Аккаунт не найден")

    return account_json(acc)

# ── Проверка подтверждения телефона (polling) ────────────
@app.get("/auth/check-phone")
async def check_phone(request: Request):
    """Фронтенд поллит этот endpoint пока пользователь подтверждает телефон в боте."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(401, detail="Нет токена")
    try:
        account_id = verify_jwt(auth_header[7:])
    except jwt.PyJWTError:
        raise HTTPException(401, detail="Токен невалиден")

    db = get_db()
    acc = db.execute("SELECT id, phone_confirmed, phone, telegram_id FROM accounts WHERE id = ?", (account_id,)).fetchone()
    db.close()

    if not acc:
        raise HTTPException(404)

    return {
        "phone_confirmed": bool(acc["phone_confirmed"]),
        "phone": acc["phone"],
        "telegram_id": acc["telegram_id"],
        "can_proceed": bool(acc["telegram_id"] and acc["phone_confirmed"]),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=3000)
