import requests, json

BASE = "https://n8n.ch-spa.com.ru"
s = requests.Session()
s.post(f"{BASE}/rest/login", json={"emailOrLdapLoginId": "shat.pomoshnik@gmail.com", "password": "1234Ko4321"})

V2_ID = "oV8dWIoAUHRkLaSb"

H = """const appConfig = $input.first().json.app_config || $input.first().json;
const baseUrl = appConfig.SUPABASE_REST_URL;
const apiKey = appConfig.SUPABASE_SERVICE_ROLE_KEY;
const headers = {"apikey": apiKey, "Authorization": "Bearer " + apiKey, "Content-Type": "application/json"};"""

# ========== Auto-Approve Cron ==========
auto_approve_code = H + """
const delayH = appConfig.AUTO_APPROVE_DELAY_HOURS || 1;
const cutoff = new Date(Date.now() - delayH * 60 * 60 * 1000).toISOString();

const resp = await fetch(baseUrl + "/submissions?purchase_status=eq.pending&timer_started_at=lte." + cutoff + "&select=*", { headers });
const pending = await resp.json();
const subs = Array.isArray(pending) ? pending : [];

let approved = 0;
for (const sub of subs) {
  await fetch(baseUrl + "/submissions?id=eq." + sub.id, {
    method: "PATCH", headers,
    body: JSON.stringify({ purchase_status: "approved", approved_at: new Date().toISOString() })
  });
  await fetch(baseUrl + "/users?telegram_id=eq." + sub.user_id, {
    method: "PATCH", headers,
    body: JSON.stringify({ purchase_status: "approved", bonus_access: "unlocked", user_state: "approved" })
  });
  await fetch(baseUrl + "/events", {
    method: "POST", headers,
    body: JSON.stringify({ user_id: sub.user_id, event_name: "submission_approved", payload: { submission_id: sub.id, package: sub.package, auto: true } })
  });
  approved++;
}

return [{ json: { approved, total: subs.length, cutoff } }];"""

# ========== Followup Cron ==========
followup_code = H + """
const followupConfig = {
  awaiting_subscription: { hours: 24, text: "Вы не закончили оформление! Подпишитесь на канал и нажмите Проверить подписку." },
  awaiting_contact: { hours: 24, text: "Остался последний шаг! Поделитесь контактом чтобы продолжить." },
  awaiting_package: { hours: 48, text: "Выберите ваш набор бонусов и получите подарки!" },
  awaiting_photo: { hours: 48, text: "Загрузите фото чека чтобы мы могли подтвердить покупку." },
  pending_approval: { hours: 6, text: "Ваша заявка обрабатывается. Бонусы будут начислены автоматически." },
  awaiting_review_marketplace: { hours: 72, text: "Оставьте отзыв и получите дополнительные бонусы!" },
  awaiting_upsell: { hours: 72, text: "Увеличьте ваш набор бонусов со скидкой!" }
};

const now = new Date();
let sent = 0;

for (const [state, cfg] of Object.entries(followupConfig)) {
  const cutoff = new Date(now - cfg.hours * 60 * 60 * 1000).toISOString();
  const resp = await fetch(baseUrl + "/users?user_state=eq." + state + "&last_seen=lte." + cutoff + "&select=telegram_id,last_followup_at&limit=50", { headers });
  const users = Array.isArray(await resp.json()) ? await resp.json() : [];

  for (const user of users) {
    if (user.last_followup_at) {
      const last = new Date(user.last_followup_at);
      if ((now - last) / 3600000 < cfg.hours) continue;
    }
    await fetch(baseUrl + "/users?telegram_id=eq." + user.telegram_id, {
      method: "PATCH", headers,
      body: JSON.stringify({ last_followup_at: now.toISOString() })
    });
    sent++;
    // Return users for Telegram node
    $json.toMessage = { chatId: user.telegram_id, text: cfg.text };
    break; // n8n can only send one message per execution from a code node
  }
}

return [{ json: { sent, toMessage: $json.toMessage || null } }];"""

# ========== Daily Report Cron ==========
report_code = H + """
const resp = await fetch(baseUrl + "/view_conversion_summary?select=*", { headers });
const rows = Array.isArray(await resp.json()) ? await resp.json() : [];
const today = rows.find(r => r.period === "today") || {};
const week = rows.find(r => r.period === "week") || {};

const pct = (a, b) => b && b > 0 ? Math.round(a / b * 100) + "%" : "-";

const text = [
  "📊 <b>CH-SPA — отчёт</b>",
  "",
  "📅 <b>За сегодня:</b>",
  "Стартов: " + (today.starts || 0),
  "Контактов: " + (today.contacts || 0),
  "Заявок: " + (today.submissions || 0),
  "Одобрено: " + (today.approved || 0),
  "Кликов: " + (today.bonus_clicks || 0),
  "Оплат: " + (today.payments || 0),
  "",
  "📆 <b>Среднее за 7 дней:</b>",
  "Стартов: " + Math.round(week.starts || 0),
  "Заявок: " + Math.round(week.submissions || 0),
  "Одобрено: " + Math.round(week.approved || 0),
  "Оплат: " + Math.round(week.payments || 0),
  "",
  "Конверсия: старт→заявка " + pct(today.submissions, today.starts) + ", заявка→одобрение " + pct(today.approved, today.submissions)
].join("\\n");

const mgrChat = appConfig.MANAGERS_GROUP_CHAT_ID;
return [{ json: { replyText: text, parseMode: "HTML", chatId: mgrChat } }];"""

# ========== Bonus Redirect Webhook ==========
bonus_redirect_code = H + """
const params = $input.first().json.params || $input.first().json.query || {};
const userId = String(params.userId || params.user_id || "").trim();
const bonusKey = String(params.bonusKey || params.bonus_key || "").trim();

if (!userId || !bonusKey) {
  return [{ json: { status: 400, body: "Missing userId or bonusKey" } }];
}

const uResp = await fetch(baseUrl + "/users?telegram_id=eq." + userId + "&select=selected_package", { headers });
const user = (Array.isArray(await uResp.json()) ? await uResp.json() : [])[0];
if (!user?.selected_package) {
  return [{ json: { status: 404, body: "User or package not found" } }];
}

const bResp = await fetch(baseUrl + "/bonuses?package=eq." + user.selected_package + "&bonus_key=eq." + bonusKey + "&select=*", { headers });
const bonus = (Array.isArray(await bResp.json()) ? await bResp.json() : [])[0];
if (!bonus?.real_url) {
  return [{ json: { status: 404, body: "Bonus not found" } }];
}

await fetch(baseUrl + "/events", {
  method: "POST", headers,
  body: JSON.stringify({ user_id: userId, event_name: "bonus_clicked", payload: { package: user.selected_package, bonus_key: bonusKey, bonus_name: bonus.bonus_name, school_name: bonus.school_name } })
});

// 302 redirect
return [{ json: { status: 302, headers: { Location: bonus.real_url } } }];"""

# ========== Payment Webhook ==========
payment_webhook_code = H + """
const body = $input.first().json.body || $input.first().json;
const event = body.event || "";
const payment = body.object || {};
const paymentId = payment.id || "";
const status = payment.status || event;

// Idempotency check
if (paymentId) {
  const check = await fetch(baseUrl + "/payments?provider_payment_id=eq." + paymentId + "&select=id", { headers });
  const existing = (Array.isArray(await check.json()) ? await check.json() : []);
  if (existing.length > 0 && existing[0].status !== "pending") {
    return [{ json: { ok: true, message: "Already processed" } }];
  }
}

if (status === "payment.succeeded" || status === "succeeded") {
  const userId = payment.metadata?.user_id || "";
  await fetch(baseUrl + "/payments", {
    method: "POST", headers,
    body: JSON.stringify({ user_id: userId, provider_payment_id: paymentId, amount: payment.amount?.value || 0, currency: payment.amount?.currency || "RUB", status: "succeeded", idempotency_key: paymentId, payload: body })
  });
  if (userId) {
    await fetch(baseUrl + "/users?telegram_id=eq." + userId, { method: "PATCH", headers, body: JSON.stringify({ user_state: "completed" }) });
  }
  await fetch(baseUrl + "/events", { method: "POST", headers, body: JSON.stringify({ user_id: userId, event_name: "payment_succeeded", payload: { payment_id: paymentId } }) });
  return [{ json: { ok: true, replyText: "Оплата прошла! Спасибо за покупку!", chatId: userId } }];
}

return [{ json: { ok: true, message: "Event ignored: " + status } }];"""

# Build the cron/webhook nodes
cron_nodes = [
    {
        "id": "cron-auto-approve",
        "name": "Auto-Approve Cron",
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1,
        "position": [0, 800],
        "parameters": {"rule": {"interval": [{"field": "minutes", "minutesInterval": 5}]}}
    },
    {
        "id": "code-auto-approve",
        "name": "Auto-Approve Worker",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [220, 800],
        "parameters": {"jsCode": auto_approve_code}
    },
    {
        "id": "cron-followup",
        "name": "Followup Cron",
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1,
        "position": [0, 960],
        "parameters": {"rule": {"interval": [{"field": "hours", "hoursInterval": 6}]}}
    },
    {
        "id": "code-followup",
        "name": "Followup Worker",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [220, 960],
        "parameters": {"jsCode": followup_code}
    },
    {
        "id": "cron-report",
        "name": "Daily Report Cron",
        "type": "n8n-nodes-base.scheduleTrigger",
        "typeVersion": 1,
        "position": [0, 1120],
        "parameters": {"rule": {"interval": [{"field": "hours", "hoursInterval": 24}]}}
    },
    {
        "id": "code-report",
        "name": "Daily Report Worker",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [220, 1120],
        "parameters": {"jsCode": report_code}
    },
    {
        "id": "tg-report",
        "name": "Send Daily Report",
        "type": "n8n-nodes-base.telegram",
        "typeVersion": 1,
        "position": [440, 1120],
        "parameters": {"text": "={{ $json.replyText }}", "additionalFields": {"reply_markup": "={{ $json.replyKeyboard || '' }}"}},
        "credentials": {"telegramApi": {"id": "b1x5cXjr8PBaOxPy", "name": "CH-SPA Bot Token"}}
    },
    {
        "id": "webhook-bonus",
        "name": "Bonus Redirect Webhook",
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 1,
        "position": [0, 1280],
        "parameters": {"httpMethod": "GET", "path": "bonus-redirect", "responseMode": "responseNode"},
        "webhookId": "bonus-redirect-v2"
    },
    {
        "id": "code-bonus-redirect",
        "name": "Bonus Redirect Worker",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [220, 1280],
        "parameters": {"jsCode": bonus_redirect_code}
    },
    {
        "id": "webhook-payment",
        "name": "Payment Webhook",
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 1,
        "position": [0, 1440],
        "parameters": {"httpMethod": "POST", "path": "payment-webhook", "responseMode": "responseNode"},
        "webhookId": "payment-webhook-v2"
    },
    {
        "id": "code-payment",
        "name": "Payment Worker",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [220, 1440],
        "parameters": {"jsCode": payment_webhook_code}
    },
    {
        "id": "tg-payment",
        "name": "Send Payment Confirm",
        "type": "n8n-nodes-base.telegram",
        "typeVersion": 1,
        "position": [440, 1440],
        "parameters": {"text": "={{ $json.replyText }}"},
        "credentials": {"telegramApi": {"id": "b1x5cXjr8PBaOxPy", "name": "CH-SPA Bot Token"}}
    },
]

# Connect the cron/webhook chains
cron_conns = {
    "Auto-Approve Cron": {"main": [[{"node": "Auto-Approve Worker", "type": "main", "index": 0}]]},
    "Followup Cron": {"main": [[{"node": "Followup Worker", "type": "main", "index": 0}]]},
    "Daily Report Cron": {"main": [[{"node": "Daily Report Worker", "type": "main", "index": 0}]]},
    "Daily Report Worker": {"main": [[{"node": "Send Daily Report", "type": "main", "index": 0}]]},
    "Bonus Redirect Webhook": {"main": [[{"node": "Bonus Redirect Worker", "type": "main", "index": 0}]]},
    "Payment Webhook": {"main": [[{"node": "Payment Worker", "type": "main", "index": 0}]]},
    "Payment Worker": {"main": [[{"node": "Send Payment Confirm", "type": "main", "index": 0}]]},
}

# Get existing, merge
resp = s.get(f"{BASE}/rest/workflows/{V2_ID}")
wf = resp.json().get('data', resp.json())
existing_nodes = wf.get('nodes', [])
existing_conns = wf.get('connections', {})

all_nodes = existing_nodes + cron_nodes
existing_conns.update(cron_conns)

resp = s.patch(f"{BASE}/rest/workflows/{V2_ID}", json={"nodes": all_nodes, "connections": existing_conns})
print(f"Update: {resp.status_code}")
if resp.ok:
    result = resp.json().get('data', resp.json())
    print(f"Total nodes: {len(result.get('nodes', []))}")
    for n in result['nodes']:
        marker = " ⚡" if "Cron" in n['name'] or "Webhook" in n['name'] else ""
        print(f"  {n['name']}{marker}")
    print(f"\\nURL: {BASE}/workflow/{V2_ID}")
else:
    print(f"Error: {resp.text[:500]}")

s.close()
