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

# ========== Branch 10: Start Review ==========
b10 = H + """
await fetch(baseUrl + "/users?telegram_id=eq." + tid, {
  method: "PATCH", headers,
  body: JSON.stringify({ user_state: "awaiting_review_marketplace", last_seen: new Date().toISOString() })
});
const text = "Выберите маркетплейс где оставили отзыв:";
const kb = '{"inline_keyboard":[[{"text":"Wildberries","callback_data":"MARKETPLACE_WB"}],[{"text":"Ozon","callback_data":"MARKETPLACE_OZON"}],[{"text":"Яндекс.Маркет","callback_data":"MARKETPLACE_YM"}]]}';
return [{ json: { ...input, replyText: text, replyKeyboard: kb, crm: {...crm, state: "awaiting_review_marketplace"} } }];"""

# ========== Branch 11: Marketplace Selected ==========
b11 = H + """
const cb = input.callback_query?.data || "";
const mpMap = {"MARKETPLACE_WB": "Wildberries", "MARKETPLACE_OZON": "Ozon", "MARKETPLACE_YM": "Яндекс.Маркет"};
const mp = mpMap[cb] || cb;
await fetch(baseUrl + "/users?telegram_id=eq." + tid, {
  method: "PATCH", headers,
  body: JSON.stringify({ user_state: "awaiting_review_screenshot", last_seen: new Date().toISOString() })
});
await fetch(baseUrl + "/events", {
  method: "POST", headers,
  body: JSON.stringify({ user_id: tid, event_name: "review_marketplace_selected", payload: { marketplace: mp } })
});
const text = "Загрузите скриншот опубликованного отзыва.";
return [{ json: { ...input, replyText: text, crm: {...crm, state: "awaiting_review_screenshot", review_marketplace: mp} } }];"""

# ========== Branch 12: Review Screenshot ==========
b12 = H + """
const photo = input.message?.photo;
let fileId = "";
if (photo && Array.isArray(photo)) fileId = photo[photo.length - 1].file_id;
await fetch(baseUrl + "/users?telegram_id=eq." + tid, {
  method: "PATCH", headers,
  body: JSON.stringify({ user_state: "awaiting_review_product_photo", last_seen: new Date().toISOString() })
});
await fetch(baseUrl + "/events", {
  method: "POST", headers,
  body: JSON.stringify({ user_id: tid, event_name: "review_screenshot_uploaded", payload: { file_id: fileId } })
});
const text = "Теперь загрузите фото распакованного товара.";
return [{ json: { ...input, replyText: text, reviewScreenshotFileId: fileId, crm: {...crm, state: "awaiting_review_product_photo"} } }];"""

# ========== Branch 13: Review Product Photo ==========
b13 = H + """
const photo = input.message?.photo;
let fileId = "";
if (photo && Array.isArray(photo)) fileId = photo[photo.length - 1].file_id;

const resp = await fetch(baseUrl + "/review_submissions", {
  method: "POST", headers,
  body: JSON.stringify({
    user_id: tid, marketplace: crm.review_marketplace || "",
    review_screenshot_file_id: input.reviewScreenshotFileId || "",
    product_photo_file_id: fileId, status: "pending"
  })
});
await fetch(baseUrl + "/users?telegram_id=eq." + tid, {
  method: "PATCH", headers,
  body: JSON.stringify({ user_state: "review_pending", last_seen: new Date().toISOString() })
});
await fetch(baseUrl + "/events", {
  method: "POST", headers,
  body: JSON.stringify({ user_id: tid, event_name: "review_product_photo_uploaded", payload: {} })
});

// Notify managers
const mgrChat = appConfig.MANAGERS_GROUP_CHAT_ID;
const notifText = "🔄 Новый отзыв на модерацию!\\nПользователь: " + tid;

return [{ json: { ...input, replyText: "Спасибо! Ваш отзыв отправлен на проверку.", notifyManagers: true, managerText: notifText, managerChatId: mgrChat, crm: {...crm, state: "review_pending"} } }];"""

# ========== Branch 23: Upsell Yes ==========
b23 = H + """
await fetch(baseUrl + "/users?telegram_id=eq." + tid, {
  method: "PATCH", headers,
  body: JSON.stringify({ user_state: "awaiting_upsell", last_seen: new Date().toISOString() })
});
await fetch(baseUrl + "/events", {
  method: "POST", headers,
  body: JSON.stringify({ user_id: tid, event_name: "upsell_accepted", payload: {} })
});
const text = "Скоро вы получите ссылку на оплату апгрейда!";
return [{ json: { ...input, replyText: text, crm: {...crm, state: "awaiting_upsell"} } }];"""

# ========== Branch 24: Upsell No ==========
b24 = H + """
await fetch(baseUrl + "/users?telegram_id=eq." + tid, {
  method: "PATCH", headers,
  body: JSON.stringify({ user_state: "completed", last_seen: new Date().toISOString() })
});
await fetch(baseUrl + "/events", {
  method: "POST", headers,
  body: JSON.stringify({ user_id: tid, event_name: "upsell_declined", payload: {} })
});
const text = "Спасибо за участие! Если передумаете — пишите.";
return [{ json: { ...input, replyText: text, crm: {...crm, state: "completed"} } }];"""

# ========== Branch 21: Admin Export ==========
b21 = H + """
const allUsers = await fetch(baseUrl + "/users?select=*&limit=1000", { headers });
const users = await allUsers.json();
const rows = Array.isArray(users) ? users : [];
let csv = "telegram_id,username,phone,user_state,selected_package,purchase_status,bonus_access\\n";
for (const u of rows) {
  csv += [u.telegram_id, u.username, u.phone, u.user_state, u.selected_package, u.purchase_status, u.bonus_access].join(",") + "\\n";
}
return [{ json: { ...input, replyText: "Экспорт:\\n\\n" + csv.substring(0, 3800), crm } }];"""

# ========== Branch 22: Admin Stats/Broadcast/User ==========
b22 = H + """
const text = input.message?.text || "";

if (text === "/stats") {
  const r = await fetch(baseUrl + "/view_conversion_summary?select=*", { headers });
  const stats = await r.json();
  let reply = "📊 Статистика:\\n";
  for (const s of (Array.isArray(stats) ? stats : [])) {
    reply += s.period + ": стартов " + s.starts + ", заявок " + s.submissions + ", одобрено " + s.approved + ", кликов " + s.bonus_clicks + ", оплат " + s.payments + "\\n";
  }
  return [{ json: { ...input, replyText: reply, crm } }];
}

if (text.startsWith("/broadcast")) {
  const msg = text.replace("/broadcast ", "").trim();
  const r = await fetch(baseUrl + "/users?select=telegram_id", { headers });
  const users = await r.json();
  const chats = (Array.isArray(users) ? users : []).map(u => u.telegram_id);
  return [{ json: { ...input, replyText: "Рассылка на " + chats.length + " пользователей.", broadcastChats: chats, broadcastMsg: msg, crm } }];
}

if (text.startsWith("/user")) {
  const uid = text.replace("/user ", "").trim();
  const r = await fetch(baseUrl + "/users?telegram_id=eq." + uid + "&select=*", { headers });
  const u = await r.json();
  const user = (Array.isArray(u) ? u[0] : u) || {};
  return [{ json: { ...input, replyText: "Пользователь: " + JSON.stringify(user, null, 2), crm } }];
}

return [{ json: { ...input, replyText: "Команды: /stats, /broadcast <текст>, /user <id>", crm } }];"""

# Build nodes
def make_code(idx, name, code, pos_y):
    return {"id": f"br{idx}-code", "name": name, "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [880, pos_y], "parameters": {"jsCode": code}}

def make_tg(idx, name, pos_y):
    return {"id": f"br{idx}-tg", "name": name, "type": "n8n-nodes-base.telegram", "typeVersion": 1, "position": [1100, pos_y], "parameters": {"text": "={{ $json.replyText }}", "additionalFields": {"reply_markup": "={{ $json.replyKeyboard || '' }}"}}, "credentials": {"telegramApi": {"id": "b1x5cXjr8PBaOxPy", "name": "CH-SPA Bot Token"}}}

branches = [
    (10, "Start Review", b10, "Send Review Start", 1880),
    (11, "Save Marketplace", b11, "Send Ask Screenshot", 2000),
    (12, "Save Rev Screenshot", b12, "Send Ask Prod Photo", 2120),
    (13, "Save Rev Prod Photo", b13, "Send Rev Pending", 2240),
    (21, "Admin Export", b21, "Send Export CSV", 2360),
    (22, "Admin Commands", b22, "Send Admin Result", 2480),
    (23, "Upsell Yes", b23, "Send Upsell Yes", 2600),
    (24, "Upsell No", b24, "Send Upsell No", 2720),
]

all_new = []
for br_idx, code_name, code, tg_name, pos_y in branches:
    all_new.append(make_code(br_idx, code_name, code, pos_y))
    all_new.append(make_tg(br_idx, tg_name, pos_y))

# Get existing
resp = s.get(f"{BASE}/rest/workflows/{V2_ID}")
wf = resp.json().get('data', resp.json())
existing_nodes = wf.get('nodes', [])
existing_conns = wf.get('connections', {})

all_nodes = existing_nodes + all_new

# Update router
router = existing_conns.get("Router", {}).get("main", [])
while len(router) < 26:
    router.append([])

for br_idx, code_name, _, tg_name, _ in branches:
    router[br_idx] = [{"node": code_name, "type": "main", "index": 0}]
    existing_conns[code_name] = {"main": [[{"node": tg_name, "type": "main", "index": 0}]]}

existing_conns["Router"] = {"main": router}

resp = s.patch(f"{BASE}/rest/workflows/{V2_ID}", json={"nodes": all_nodes, "connections": existing_conns})
print(f"Update: {resp.status_code}")
if resp.ok:
    result = resp.json().get('data', resp.json())
    print(f"Total nodes: {len(result.get('nodes', []))}")
    for n in result['nodes']:
        print(f"  {n['name']}")
    print(f"\nOpen: {BASE}/workflow/{V2_ID}")
else:
    print(f"Error: {resp.text[:400]}")

s.close()
