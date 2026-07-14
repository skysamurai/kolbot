# kolbot — CH-SPA Loyalty Telegram Bot

Telegram bot for a loyalty program with receipt scanning, bonus tracking, and admin panel. Uses raw Telegram HTTP API + FastAPI backends + n8n workflow automation.

## Key Features

- **Telegram bot:** receipt photo upload → AI parsing → bonus accrual
- **n8n workflows:** 10+ automated workflows for user onboarding, bonus processing, daily reports, routing
- **WebApp auth:** Telegram Mini App initData validation (HMAC-SHA256)
- **Admin panel:** user management, stats dashboard, bonus tracking
- **Multi-backend:** FastAPI for WebApp auth + admin API

## Stack

| Layer | Technology |
|-------|-----------|
| Bot | Raw Telegram HTTP API (httpx), no framework |
| Backend | FastAPI × 2 (WebApp auth + Admin) |
| DB | Supabase (PostgreSQL) |
| Workflows | n8n (10+ JavaScript nodes) |
| AI | DeepSeek API (receipt parsing) |
| Auth | HMAC-SHA256 (Telegram initData) |

## Architecture

```
Telegram User ──→ Bot (httpx) ──→ Supabase
                      │
              ┌───────┴───────┐
              │               │
         FastAPI WebApp   FastAPI Admin
         (initData auth)  (JWT auth)
              │               │
         n8n Workflows ←─────┘
```

## Project Structure

```
bot/                    Telegram bot (raw API)
admin_web/              FastAPI admin panel + JWT auth
example_webapp_auth/    FastAPI WebApp with Telegram initData validation
workflow_v2/            n8n workflow JavaScript nodes
```

## Quick Start

```bash
pip install fastapi uvicorn httpx
python bot/bot.py              # Telegram bot
uvicorn admin_web.backend:app  # Admin panel
```
