"""
Admin web panel backend for CH-SPA bot.
Serves admin HTML + REST API for user/ref/stats management.
"""
import os, sys, json, secrets
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# Add bot/ to path to import db
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'bot'))
from db import (
    init_db, get_all_users, get_user, get_conversion_stats,
    kv_get_int, kv_set,
    get_user_purchases, get_user_receipts, get_unburned_purchase_count,
    grant_bonus_to_user, remove_bonus_from_user, remove_all_bonuses_from_user,
    get_granted_bonuses,
)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Auth
ADMIN_PASSWORD = os.getenv('ADMIN_PASSWORD', 'admin123')
JWT_SECRET = os.getenv('JWT_SECRET', secrets.token_hex(32))
JWT_TTL = timedelta(hours=24)

import jwt as pyjwt

def make_admin_token() -> str:
    payload = {"role": "admin", "exp": datetime.now(timezone.utc) + JWT_TTL}
    return pyjwt.encode(payload, JWT_SECRET, algorithm="HS256")

def verify_admin(request: Request):
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(401, detail="No token")
    try:
        payload = pyjwt.decode(auth[7:], JWT_SECRET, algorithms=["HS256"])
        if payload.get("role") != "admin":
            raise HTTPException(403)
        return payload
    except pyjwt.PyJWTError:
        raise HTTPException(401, detail="Invalid token")

BONUS_TIERS = [
    {'bonus_key': 'bonus_1', 'bonus_name': 'Вводный урок'},
    {'bonus_key': 'bonus_2', 'bonus_name': 'Мини-курс'},
    {'bonus_key': 'bonus_3', 'bonus_name': 'Мастер-класс'},
]

# ── Models ───────────────────────────────────────────────
class LoginRequest(BaseModel):
    password: str

class GrantRevokeRequest(BaseModel):
    bonus_key: str  # "bonus_1", "bonus_2", "bonus_3", or "ALL"

class RefSettingsUpdate(BaseModel):
    l1: int = None
    l2: int = None
    l3: int = None

# ── Auth ──────────────────────────────────────────────────
@app.post("/api/auth/login")
async def login(body: LoginRequest):
    if body.password != ADMIN_PASSWORD:
        raise HTTPException(401, detail="Wrong password")
    return {"token": make_admin_token()}

@app.get("/api/auth/check")
async def check(request: Request):
    verify_admin(request)
    return {"status": "ok"}

# ── Users ─────────────────────────────────────────────────
@app.get("/api/users")
async def list_users(
    request: Request,
    page: int = Query(0, ge=0),
    per_page: int = Query(20, ge=1, le=100),
    search: str = Query(""),
):
    verify_admin(request)
    users = get_all_users()
    # search filter
    if search:
        q = search.lower()
        users = [u for u in users if
                 q in str(u.get('telegram_id', '')) or
                 q in (u.get('first_name', '') or '').lower() or
                 q in (u.get('last_name', '') or '').lower() or
                 q in (u.get('username', '') or '').lower() or
                 q in (u.get('phone', '') or '').lower() or
                 q in (u.get('ref_code', '') or '').lower()]

    total = len(users)
    total_pages = max(1, (total + per_page - 1) // per_page)
    start = page * per_page
    chunk = users[start:start + per_page]

    result = []
    for u in chunk:
        utid = u['telegram_id']
        pcount = get_unburned_purchase_count(utid)
        granted = get_granted_bonuses(utid)
        result.append({
            'telegram_id': utid,
            'first_name': u.get('first_name'),
            'last_name': u.get('last_name'),
            'username': u.get('username'),
            'phone': u.get('phone'),
            'user_state': u.get('user_state'),
            'ref_code': u.get('ref_code'),
            'purchase_count': pcount,
            'granted_bonuses': list(granted),
            'created_at': u.get('created_at', '')[:19] if u.get('created_at') else '',
        })

    return {
        'users': result,
        'page': page,
        'per_page': per_page,
        'total': total,
        'total_pages': total_pages,
    }

# ── User Detail ──────────────────────────────────────────
@app.get("/api/users/{telegram_id}")
async def user_detail(telegram_id: int, request: Request):
    verify_admin(request)
    u = get_user(telegram_id)
    if not u:
        raise HTTPException(404, detail="User not found")

    purchases = get_user_purchases(telegram_id, unburned_only=False)
    receipts = get_user_receipts(telegram_id, unburned_only=False)
    unburned = get_unburned_purchase_count(telegram_id)
    granted = get_granted_bonuses(telegram_id)

    # Referral info
    referrer = get_user(u.get('referred_by')) if u.get('referred_by') else None
    ref_l2 = get_user(u.get('referred_by_l2')) if u.get('referred_by_l2') else None
    ref_l3 = get_user(u.get('referred_by_l3')) if u.get('referred_by_l3') else None

    return {
        'telegram_id': telegram_id,
        'first_name': u.get('first_name'),
        'last_name': u.get('last_name'),
        'username': u.get('username'),
        'phone': u.get('phone'),
        'user_state': u.get('user_state'),
        'ref_code': u.get('ref_code'),
        'created_at': u.get('created_at', '')[:19] if u.get('created_at') else '',
        'granted_bonuses': list(granted),
        'purchases': [
            {'product_name': p['product_name'], 'quantity': p['quantity'],
             'price': p['price'], 'is_burned': bool(p['is_burned']),
             'burned_for': p.get('burned_for_bonus'),
             'created_at': p.get('created_at', '')[:19] if p.get('created_at') else ''}
            for p in purchases
        ],
        'receipts': [
            {'receipt_number': r['receipt_number'], 'receipt_url': r.get('receipt_url'),
             'is_used': bool(r['is_used']), 'used_for': r.get('used_for_bonus'),
             'created_at': r.get('created_at', '')[:19] if r.get('created_at') else ''}
            for r in receipts
        ],
        'total_purchases': sum(p['quantity'] for p in purchases),
        'unburned_purchases': unburned,
        'total_receipts': len(receipts),
        'used_receipts': sum(1 for r in receipts if r['is_used']),
        'referrer': {'telegram_id': referrer['telegram_id'], 'first_name': referrer.get('first_name')} if referrer else None,
        'referrer_l2': {'telegram_id': ref_l2['telegram_id'], 'first_name': ref_l2.get('first_name')} if ref_l2 else None,
        'referrer_l3': {'telegram_id': ref_l3['telegram_id'], 'first_name': ref_l3.get('first_name')} if ref_l3 else None,
    }

# ── Grant / Revoke ──────────────────────────────────────
@app.post("/api/users/{telegram_id}/grant")
async def grant_bonus(telegram_id: int, body: GrantRevokeRequest, request: Request):
    verify_admin(request)
    u = get_user(telegram_id)
    if not u:
        raise HTTPException(404, detail="User not found")

    if body.bonus_key == 'ALL':
        for bk in ['bonus_1', 'bonus_2', 'bonus_3']:
            grant_bonus_to_user(telegram_id, bk)
    else:
        grant_bonus_to_user(telegram_id, body.bonus_key)

    granted = get_granted_bonuses(telegram_id)
    return {"status": "ok", "granted_bonuses": list(granted)}

@app.post("/api/users/{telegram_id}/revoke")
async def revoke_bonus(telegram_id: int, body: GrantRevokeRequest, request: Request):
    verify_admin(request)
    u = get_user(telegram_id)
    if not u:
        raise HTTPException(404, detail="User not found")

    if body.bonus_key == 'ALL':
        remove_all_bonuses_from_user(telegram_id)
    else:
        remove_bonus_from_user(telegram_id, body.bonus_key)

    granted = get_granted_bonuses(telegram_id)
    return {"status": "ok", "granted_bonuses": list(granted)}

# ── Referral Settings ────────────────────────────────────
@app.get("/api/ref-settings")
async def get_ref_settings(request: Request):
    verify_admin(request)
    return {
        'l1': kv_get_int('ref_commission_l1', 10),
        'l2': kv_get_int('ref_commission_l2', 5),
        'l3': kv_get_int('ref_commission_l3', 3),
    }

@app.put("/api/ref-settings")
async def update_ref_settings(body: RefSettingsUpdate, request: Request):
    verify_admin(request)
    updates = {}
    if body.l1 is not None:
        if body.l1 < 0 or body.l1 > 100:
            raise HTTPException(400, detail="L1 must be 0-100")
        kv_set('ref_commission_l1', str(body.l1))
        updates['l1'] = body.l1
    if body.l2 is not None:
        if body.l2 < 0 or body.l2 > 100:
            raise HTTPException(400, detail="L2 must be 0-100")
        kv_set('ref_commission_l2', str(body.l2))
        updates['l2'] = body.l2
    if body.l3 is not None:
        if body.l3 < 0 or body.l3 > 100:
            raise HTTPException(400, detail="L3 must be 0-100")
        kv_set('ref_commission_l3', str(body.l3))
        updates['l3'] = body.l3

    return {"status": "ok", "updated": updates}

# ── Stats ─────────────────────────────────────────────────
@app.get("/api/stats")
async def stats(request: Request):
    verify_admin(request)
    return get_conversion_stats()

# ── Export CSV ───────────────────────────────────────────
@app.get("/api/export")
async def export_csv(request: Request):
    verify_admin(request)
    users = get_all_users()
    lines = ["telegram_id,username,first_name,last_name,phone,user_state,ref_code,referred_by,referred_by_l2,referred_by_l3,purchase_count,granted_bonuses,created_at"]
    for u in users:
        pcount = get_unburned_purchase_count(u['telegram_id'])
        granted = ','.join(sorted(get_granted_bonuses(u['telegram_id'])))
        lines.append(
            f"{u.get('telegram_id','')},{u.get('username','')},{u.get('first_name','')},{u.get('last_name','')},{u.get('phone','')},{u.get('user_state','')},{u.get('ref_code','')},{u.get('referred_by','')},{u.get('referred_by_l2','')},{u.get('referred_by_l3','')},{pcount},{granted},{u.get('created_at','')}"
        )
    return {"csv": "\n".join(lines), "total": len(users)}

# ── Serve HTML ───────────────────────────────────────────
HTML_PATH = os.path.join(os.path.dirname(__file__), 'index.html')

@app.get("/")
@app.get("/admin")
async def serve_admin():
    if os.path.exists(HTML_PATH):
        return HTMLResponse(open(HTML_PATH, encoding='utf-8').read())
    return HTMLResponse("<h1>Admin panel not found</h1>", status_code=404)


if __name__ == "__main__":
    import uvicorn
    init_db()
    print("Admin web server starting on http://0.0.0.0:8001")
    uvicorn.run(app, host="0.0.0.0", port=8001)
