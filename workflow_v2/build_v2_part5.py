import requests, json

BASE = "https://n8n.ch-spa.com.ru"
s = requests.Session()
s.post(f"{BASE}/rest/login", json={"emailOrLdapLoginId": "shat.pomoshnik@gmail.com", "password": "1234Ko4321"})

V2_ID = "oV8dWIoAUHRkLaSb"

H = """const input = $input.first().json;
const crm = input.crm || {};
const appConfig = input.app_config;
const baseUrl = appConfig.SUPABASE_REST_URL;
const apiKey = appConfig.SUPABASE_SERVICE_ROLE_KEY;
const headers = {"apikey": apiKey, "Authorization": "Bearer " + apiKey, "Content-Type": "application/json"};
const tid = crm.telegram_id;"""

# ========== Branch 8: Admin Manual Approve Purchase ==========
b8_code = H + """
const cb = input.callback_query?.data || "";
const parts = cb.split("|");
const submissionId = parts[1] || "";
const fromId = String(input.callback_query?.from?.id || "");

if (!submissionId) return [{ json: { ...input, replyText: "Ошибка: нет ID заявки" } }];

// Idempotency check
const checkResp = await fetch(baseUrl + "/submissions?id=eq." + submissionId + "&select=*", { headers });
const subs = await checkResp.json();
const sub = (Array.isArray(subs) ? subs : [])[0];

if (!sub) return [{ json: { ...input, replyText: "Заявка не найдена" } }];
if (sub.purchase_status !== "pending") return [{ json: { ...input, replyText: "Заявка уже обработана: " + sub.purchase_status } }];

// Approve
await fetch(baseUrl + "/submissions?id=eq." + submissionId, {
  method: "PATCH", headers,
  body: JSON.stringify({ purchase_status: "approved", approved_at: new Date().toISOString(), decided_by: fromId })
});
await fetch(baseUrl + "/users?telegram_id=eq." + sub.user_id, {
  method: "PATCH", headers,
  body: JSON.stringify({ purchase_status: "approved", bonus_access: "unlocked", user_state: "approved" })
});
await fetch(baseUrl + "/events", {
  method: "POST", headers,
  body: JSON.stringify({ user_id: sub.user_id, event_name: "submission_approved", payload: { submission_id: submissionId, by: fromId } })
});

// Notify user
const bonusResp = await fetch(baseUrl + "/bonuses?package=eq." + (sub.package || "standard") + "&is_active=eq.true&select=*", { headers });
const bonuses = Array.isArray(await bonusResp.json()) ? await bonusResp.json() : [];
const bonusList = bonuses.map((b, i) => (i + 1) + ". " + b.bonus_name).join("\\n");

const text = "✅ Админ одобрил заявку!\\n\\nВаши бонусы:\\n" + bonusList;
const redirectBase = appConfig.PAYMENT_RETURN_URL || (appConfig.SUPABASE_URL + "/redirect");
const kb = JSON.stringify({
  inline_keyboard: bonuses.map(b => [{ text: "🎁 " + b.bonus_name, url: redirectBase + "/r/" + sub.user_id + "/" + b.bonus_key }])
});

return [{ json: { ...input, replyText: "✅ Заявка #" + submissionId + " одобрена.", notifyUser: true, userText: text, userKeyboard: kb, userChatId: sub.user_id } }];"""

# ========== Branch 9: Admin Manual Reject Purchase ==========
b9_code = H + """
const cb = input.callback_query?.data || "";
const parts = cb.split("|");
const submissionId = parts[1] || "";
const fromId = String(input.callback_query?.from?.id || "");

if (!submissionId) return [{ json: { ...input, replyText: "Ошибка: нет ID заявки" } }];

const checkResp = await fetch(baseUrl + "/submissions?id=eq." + submissionId + "&select=*", { headers });
const subs = await checkResp.json();
const sub = (Array.isArray(subs) ? subs : [])[0];

if (!sub) return [{ json: { ...input, replyText: "Заявка не найдена" } }];
if (sub.purchase_status !== "pending") return [{ json: { ...input, replyText: "Заявка уже обработана" } }];

await fetch(baseUrl + "/submissions?id=eq." + submissionId, {
  method: "PATCH", headers,
  body: JSON.stringify({ purchase_status: "rejected", decided_by: fromId, decided_at: new Date().toISOString() })
});
await fetch(baseUrl + "/users?telegram_id=eq." + sub.user_id, {
  method: "PATCH", headers,
  body: JSON.stringify({ purchase_status: "rejected", user_state: "awaiting_photo" })
});
await fetch(baseUrl + "/events", {
  method: "POST", headers,
  body: JSON.stringify({ user_id: sub.user_id, event_name: "submission_rejected", payload: { submission_id: submissionId, by: fromId } })
});

const text = "❌ Ваша заявка отклонена. Пожалуйста, загрузите корректное фото чека.";

return [{ json: { ...input, replyText: "❌ Заявка #" + submissionId + " отклонена.", notifyUser: true, userText: text, userChatId: sub.user_id } }];"""

# ========== Branch 14: Admin Approve Review ==========
b14_code = H + """
const cb = input.callback_query?.data || "";
const reviewId = cb.split("|")[1] || "";
const fromId = String(input.callback_query?.from?.id || "");

if (!reviewId) return [{ json: { ...input, replyText: "Ошибка: нет ID отзыва" } }];

const checkResp = await fetch(baseUrl + "/review_submissions?id=eq." + reviewId + "&select=*", { headers });
const reviews = await checkResp.json();
const rev = (Array.isArray(reviews) ? reviews : [])[0];
if (!rev) return [{ json: { ...input, replyText: "Отзыв не найден" } }];
if (rev.status !== "pending") return [{ json: { ...input, replyText: "Отзыв уже обработан" } }];

await fetch(baseUrl + "/review_submissions?id=eq." + reviewId, {
  method: "PATCH", headers,
  body: JSON.stringify({ status: "approved", decided_by: fromId, decided_at: new Date().toISOString() })
});
await fetch(baseUrl + "/users?telegram_id=eq." + rev.user_id, {
  method: "PATCH", headers,
  body: JSON.stringify({ user_state: "review_approved", last_seen: new Date().toISOString() })
});
await fetch(baseUrl + "/events", {
  method: "POST", headers,
  body: JSON.stringify({ user_id: rev.user_id, event_name: "review_approved", payload: { review_id: reviewId } })
});

// Offer upsell
const textUp = "🎉 Отзыв подтверждён!\\n\\nХотите увеличить ваш набор бонусов со скидкой?";
const kb = JSON.stringify({
  inline_keyboard: [
    [{ text: "🔥 Увеличить подарок", callback_data: "UPSELL_YES" }],
    [{ text: "❌ Нет, спасибо", callback_data: "UPSELL_NO" }]
  ]
});

return [{ json: { ...input, replyText: "✅ Отзыв #" + reviewId + " одобрен.", notifyUser: true, userText: textUp, userKeyboard: kb, userChatId: rev.user_id } }];"""

# ========== Branch 15: Admin Reject Review ==========
b15_code = H + """
const cb = input.callback_query?.data || "";
const reviewId = cb.split("|")[1] || "";
const fromId = String(input.callback_query?.from?.id || "");

if (!reviewId) return [{ json: { ...input, replyText: "Ошибка: нет ID отзыва" } }];

const checkResp = await fetch(baseUrl + "/review_submissions?id=eq." + reviewId + "&select=*", { headers });
const reviews = await checkResp.json();
const rev = (Array.isArray(reviews) ? reviews : [])[0];
if (!rev) return [{ json: { ...input, replyText: "Отзыв не найден" } }];
if (rev.status !== "pending") return [{ json: { ...input, replyText: "Отзыв уже обработан" } }];

await fetch(baseUrl + "/review_submissions?id=eq." + reviewId, {
  method: "PATCH", headers,
  body: JSON.stringify({ status: "rejected", decided_by: fromId, decided_at: new Date().toISOString() })
});
await fetch(baseUrl + "/users?telegram_id=eq." + rev.user_id, {
  method: "PATCH", headers,
  body: JSON.stringify({ user_state: "awaiting_review_screenshot", last_seen: new Date().toISOString() })
});
await fetch(baseUrl + "/events", {
  method: "POST", headers,
  body: JSON.stringify({ user_id: rev.user_id, event_name: "review_rejected", payload: { review_id: reviewId } })
});

return [{ json: { ...input, replyText: "❌ Отзыв #" + reviewId + " отклонён.", notifyUser: true, userText: "Ваш отзыв отклонён. Загрузите корректный скриншот.", userChatId: rev.user_id } }];"""

# ========== FIXED: Followup Cron — multi-user support ==========
followup_fixed = """const appConfig = $input.first().json.app_config || $input.first().json;
const baseUrl = appConfig.SUPABASE_REST_URL;
const apiKey = appConfig.SUPABASE_SERVICE_ROLE_KEY;
const headers = {"apikey": apiKey, "Authorization": "Bearer " + apiKey, "Content-Type": "application/json"};

const followupConfig = {
  awaiting_subscription: { hours: 24, text: "Вы не закончили оформление! Подпишитесь на канал и нажмите Проверить подписку.", kb: '[{"text":"Проверить подписку","callback_data":"SUB_CONFIRMED"}]' },
  awaiting_contact: { hours: 24, text: "Остался последний шаг! Поделитесь контактом чтобы продолжить.", kb: '[{"text":"Поделиться контактом","request_contact":true}]' },
  awaiting_package: { hours: 48, text: "Выберите ваш набор бонусов и получите подарки!", kb: '[{"text":"1 варежка","callback_data":"PACKAGE_STANDARD"},{"text":"1+2 варежки","callback_data":"PACKAGE_PREMIUM"},{"text":"VIP","callback_data":"PACKAGE_VIP"}]' },
  awaiting_photo: { hours: 48, text: "Загрузите фото чека чтобы мы могли подтвердить покупку.", kb: null },
  pending_approval: { hours: 6, text: "Ваша заявка обрабатывается. Бонусы будут начислены автоматически.", kb: null },
  awaiting_review_marketplace: { hours: 72, text: "Оставьте отзыв и получите дополнительные бонусы!", kb: '[{"text":"Wildberries","callback_data":"MARKETPLACE_WB"},{"text":"Ozon","callback_data":"MARKETPLACE_OZON"}]' },
  awaiting_upsell: { hours: 72, text: "Увеличьте ваш набор бонусов со скидкой!", kb: '[{"text":"Увеличить","callback_data":"UPSELL_YES"},{"text":"Нет","callback_data":"UPSELL_NO"}]' }
};

const now = new Date();
const results = [];

for (const [state, cfg] of Object.entries(followupConfig)) {
  const cutoff = new Date(now - cfg.hours * 60 * 60 * 1000).toISOString();
  const resp = await fetch(baseUrl + "/users?user_state=eq." + state + "&last_seen=lte." + cutoff + "&select=telegram_id,last_followup_at&limit=20", { headers });
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
    await fetch(baseUrl + "/events", {
      method: "POST", headers,
      body: JSON.stringify({ user_id: user.telegram_id, event_name: "followup_sent", payload: { state } })
    });

    const replyMarkup = cfg.kb ? '{"inline_keyboard":[[' + cfg.kb + ']]}' : "";
    results.push({
      chatId: user.telegram_id,
      text: cfg.text,
      replyKeyboard: replyMarkup || undefined
    });
  }
}

if (results.length === 0) {
  return [{ json: { done: true, sent: 0 } }];
}
return results.map(r => ({ json: r }));"""

# ========== FIXED: Auto-Approve — send messages to users ==========
auto_approve_fixed = """const appConfig = $input.first().json.app_config || $input.first().json;
const baseUrl = appConfig.SUPABASE_REST_URL;
const apiKey = appConfig.SUPABASE_SERVICE_ROLE_KEY;
const headers = {"apikey": apiKey, "Authorization": "Bearer " + apiKey, "Content-Type": "application/json"};

const delayH = appConfig.AUTO_APPROVE_DELAY_HOURS || 1;
const cutoff = new Date(Date.now() - delayH * 60 * 60 * 1000).toISOString();
const redirectBase = appConfig.PAYMENT_RETURN_URL || (appConfig.SUPABASE_URL + "/redirect");

const resp = await fetch(baseUrl + "/submissions?purchase_status=eq.pending&timer_started_at=lte." + cutoff + "&select=*&limit=10", { headers });
const subs = Array.isArray(await resp.json()) ? await resp.json() : [];

const results = [];
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

  // Get bonuses for this user's package
  const bResp = await fetch(baseUrl + "/bonuses?package=eq." + (sub.package || "standard") + "&is_active=eq.true&select=*", { headers });
  const bonuses = Array.isArray(await bResp.json()) ? await bResp.json() : [];
  const bonusList = bonuses.map((b, i) => (i + 1) + ". " + b.bonus_name).join("\\n");

  const text = "✅ Ваша заявка одобрена!\\n\\nПакет: " + sub.package + "\\n\\nВаши бонусы:\\n" + bonusList;
  const kb = JSON.stringify({
    inline_keyboard: bonuses.map(b => [{ text: "🎁 " + b.bonus_name, url: redirectBase + "/r/" + sub.user_id + "/" + b.bonus_key }])
  });

  results.push({ chatId: sub.user_id, text, replyKeyboard: kb });
}

if (results.length === 0) return [{ json: { done: true, approved: 0 } }];
return results.map(r => ({ json: r }));"""

# Build nodes
def make_code(idx, name, code, pos_y):
    return {"id": idx, "name": name, "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [880, pos_y], "parameters": {"jsCode": code}}

def make_tg(idx, name, pos_y):
    return {"id": idx, "name": name, "type": "n8n-nodes-base.telegram", "typeVersion": 1, "position": [1100, pos_y], "parameters": {"text": "={{ $json.replyText }}", "additionalFields": {"reply_markup": "={{ $json.replyKeyboard || '' }}"}}, "credentials": {"telegramApi": {"id": "b1x5cXjr8PBaOxPy", "name": "CH-SPA Bot Token"}}}

new_branches = [
    (8, "Admin Approve Purchase", b8_code, "Send Approve Purchase", 2960),
    (9, "Admin Reject Purchase", b9_code, "Send Reject Purchase", 3080),
    (14, "Admin Approve Review", b14_code, "Send Approve Review", 3200),
    (15, "Admin Reject Review", b15_code, "Send Reject Review", 3320),
]

all_new = []
router_updates = []
for br_idx, code_name, code, tg_name, pos_y in new_branches:
    c_node = make_code(f"br{br_idx}-code-v5", code_name, code, pos_y)
    t_node = make_tg(f"br{br_idx}-tg-v5", tg_name, pos_y)
    all_new.append(c_node)
    all_new.append(t_node)
    router_updates.append((br_idx, code_name, tg_name))

# Get existing, merge
resp = s.get(f"{BASE}/rest/workflows/{V2_ID}")
wf = resp.json().get('data', resp.json())
existing_nodes = wf.get('nodes', [])
existing_conns = wf.get('connections', {})

# Update existing nodes with fixed code
for node in existing_nodes:
    if node['name'] == 'Followup Worker':
        node['parameters']['jsCode'] = followup_fixed
        print("Fixed Followup Worker")
    elif node['name'] == 'Auto-Approve Worker':
        node['parameters']['jsCode'] = auto_approve_fixed
        print("Fixed Auto-Approve Worker")

# Add new branch nodes
all_nodes = existing_nodes + all_new

# Update router connections
router = existing_conns.get("Router", {}).get("main", [])
while len(router) < 26:
    router.append([])

for br_idx, code_name, tg_name in router_updates:
    router[br_idx] = [{"node": code_name, "type": "main", "index": 0}]
    existing_conns[code_name] = {"main": [[{"node": tg_name, "type": "main", "index": 0}]]}

existing_conns["Router"] = {"main": router}

# Add Telegram sender for followup results
followup_tg = {
    "id": "tg-followup-v2",
    "name": "Send Followup Messages",
    "type": "n8n-nodes-base.telegram",
    "typeVersion": 1,
    "position": [440, 960],
    "parameters": {"text": "={{ $json.text }}", "additionalFields": {"reply_markup": "={{ $json.replyKeyboard || '' }}"}},
    "credentials": {"telegramApi": {"id": "b1x5cXjr8PBaOxPy", "name": "CH-SPA Bot Token"}}
}
all_nodes.append(followup_tg)
existing_conns["Followup Worker"] = {"main": [[{"node": "Send Followup Messages", "type": "main", "index": 0}]]}

# Add Telegram sender for auto-approve results
auto_approve_tg = {
    "id": "tg-auto-approve-v2",
    "name": "Send Approve Messages",
    "type": "n8n-nodes-base.telegram",
    "typeVersion": 1,
    "position": [440, 800],
    "parameters": {"text": "={{ $json.text }}", "additionalFields": {"reply_markup": "={{ $json.replyKeyboard || '' }}"}},
    "credentials": {"telegramApi": {"id": "b1x5cXjr8PBaOxPy", "name": "CH-SPA Bot Token"}}
}
all_nodes.append(auto_approve_tg)
existing_conns["Auto-Approve Worker"] = {"main": [[{"node": "Send Approve Messages", "type": "main", "index": 0}]]}

# Upload
resp = s.patch(f"{BASE}/rest/workflows/{V2_ID}", json={"nodes": all_nodes, "connections": existing_conns})
print(f"\\nUpdate: {resp.status_code}")
if resp.ok:
    result = resp.json().get('data', resp.json())
    print(f"Total nodes: {len(result.get('nodes', []))}")
    for n in result['nodes']:
        print(f"  {n['name']}")
    print(f"\\nWorkflow: {BASE}/workflow/{V2_ID}")
else:
    print(f"Error: {resp.text[:500]}")

s.close()
