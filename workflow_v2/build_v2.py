import requests, json

BASE = "https://n8n.ch-spa.com.ru"
s = requests.Session()
s.post(f"{BASE}/rest/login", json={"emailOrLdapLoginId": "shat.pomoshnik@gmail.com", "password": "1234Ko4321"})

V2_ID = "oV8dWIoAUHRkLaSb"

# ==========================================
# Branch 0: /start
# ==========================================
b0_code = """const input = $input.first().json;
const crm = input.crm || {};
const firstName = crm.first_name || "";
const appConfig = input.app_config;
const baseUrl = appConfig.SUPABASE_REST_URL;
const apiKey = appConfig.SUPABASE_SERVICE_ROLE_KEY;
const headers = {"apikey": apiKey, "Authorization": "Bearer " + apiKey, "Content-Type": "application/json"};
const tid = crm.telegram_id;

await fetch(baseUrl + "/users?telegram_id=eq." + tid, {
  method: "PATCH", headers,
  body: JSON.stringify({ user_state: "new", last_seen: new Date().toISOString() })
});
await fetch(baseUrl + "/events", {
  method: "POST", headers,
  body: JSON.stringify({ user_id: tid, event_name: "start", payload: {} })
});

const text = "Привет" + (firstName ? ", " + firstName : "") + "!\\nДобро пожаловать в CH-SPA!\\n\\nПодпишитесь на наш канал и нажмите Проверить подписку чтобы получить бонусы.";
const kb = '{"inline_keyboard":[[{"text":"Проверить подписку","callback_data":"SUB_CONFIRMED"}]]}';

return [{ json: { ...input, replyText: text, replyKeyboard: kb, crm: {...crm, state: "awaiting_subscription"} } }];"""

# ==========================================
# Branch 1: Start Purchase
# ==========================================
b1_code = """const input = $input.first().json;
const crm = input.crm || {};
const appConfig = input.app_config;
const baseUrl = appConfig.SUPABASE_REST_URL;
const apiKey = appConfig.SUPABASE_SERVICE_ROLE_KEY;
const headers = {"apikey": apiKey, "Authorization": "Bearer " + apiKey, "Content-Type": "application/json"};
const tid = crm.telegram_id;

await fetch(baseUrl + "/users?telegram_id=eq." + tid, {
  method: "PATCH", headers,
  body: JSON.stringify({ user_state: "awaiting_subscription", last_seen: new Date().toISOString() })
});

const text = "Подпишитесь на канал @ch_spa и нажмите кнопку ниже";
const kb = '{"inline_keyboard":[[{"text":"Проверить подписку","callback_data":"SUB_CONFIRMED"}]]}';

return [{ json: { ...input, replyText: text, replyKeyboard: kb, crm: {...crm, state: "awaiting_subscription"} } }];"""

# ==========================================
# Branch 2: Subscription confirmed
# ==========================================
b2_code = """const input = $input.first().json;
const crm = input.crm || {};
const appConfig = input.app_config;
const baseUrl = appConfig.SUPABASE_REST_URL;
const apiKey = appConfig.SUPABASE_SERVICE_ROLE_KEY;
const headers = {"apikey": apiKey, "Authorization": "Bearer " + apiKey, "Content-Type": "application/json"};
const tid = crm.telegram_id;

await fetch(baseUrl + "/users?telegram_id=eq." + tid, {
  method: "PATCH", headers,
  body: JSON.stringify({ user_state: "awaiting_contact", last_seen: new Date().toISOString() })
});
await fetch(baseUrl + "/events", {
  method: "POST", headers,
  body: JSON.stringify({ user_id: tid, event_name: "subscription_confirmed", payload: {} })
});

const text = "Отлично! Теперь поделитесь номером телефона чтобы продолжить.";
const kb = '{"inline_keyboard":[[{"text":"Поделиться контактом","request_contact":true}]]}';

return [{ json: { ...input, replyText: text, replyKeyboard: kb, crm: {...crm, state: "awaiting_contact"} } }];"""

# ==========================================
# Branch 3: Contact received
# ==========================================
b3_code = """const input = $input.first().json;
const crm = input.crm || {};
const phone = input.message?.contact?.phone_number || "";
const appConfig = input.app_config;
const baseUrl = appConfig.SUPABASE_REST_URL;
const apiKey = appConfig.SUPABASE_SERVICE_ROLE_KEY;
const headers = {"apikey": apiKey, "Authorization": "Bearer " + apiKey, "Content-Type": "application/json"};
const tid = crm.telegram_id;

await fetch(baseUrl + "/users?telegram_id=eq." + tid, {
  method: "PATCH", headers,
  body: JSON.stringify({ phone: phone, user_state: "awaiting_package", last_seen: new Date().toISOString() })
});
await fetch(baseUrl + "/events", {
  method: "POST", headers,
  body: JSON.stringify({ user_id: tid, event_name: "contact_saved", payload: { phone: phone } })
});

const text = "Выберите ваш набор бонусов:";
const kb = '{"inline_keyboard":[[{"text":"1 варежка (3000 руб.)","callback_data":"PACKAGE_STANDARD"}],[{"text":"1+2 варежки (7000 руб.)","callback_data":"PACKAGE_PREMIUM"}],[{"text":"VIP: 1+2+5 варежек (11000 руб.)","callback_data":"PACKAGE_VIP"}]]}';

return [{ json: { ...input, replyText: text, replyKeyboard: kb, crm: {...crm, state: "awaiting_package"} } }];"""

# ==========================================
# Branch 7: Photo uploaded -> Create Submission
# ==========================================
b7_code = """const input = $input.first().json;
const crm = input.crm || {};
const photo = input.message?.photo;
let fileId = "";
if (photo && Array.isArray(photo)) { fileId = photo[photo.length - 1].file_id; }
const appConfig = input.app_config;
const baseUrl = appConfig.SUPABASE_REST_URL;
const apiKey = appConfig.SUPABASE_SERVICE_ROLE_KEY;
const headers = {"apikey": apiKey, "Authorization": "Bearer " + apiKey, "Content-Type": "application/json", "Prefer": "return=representation"};
const tid = crm.telegram_id;
const pkg = crm.selected_package || "standard";

const resp = await fetch(baseUrl + "/submissions", {
  method: "POST", headers,
  body: JSON.stringify({
    user_id: tid, package: pkg, photo_file_id: fileId,
    purchase_status: "pending", timer_started_at: new Date().toISOString()
  })
});

if (resp.status === 409) {
  return [{ json: { ...input, replyText: "У вас уже есть заявка на модерации. Ожидайте.", crm } }];
}

await fetch(baseUrl + "/users?telegram_id=eq." + tid, {
  method: "PATCH", headers,
  body: JSON.stringify({ user_state: "pending_approval", purchase_status: "pending", last_seen: new Date().toISOString() })
});
await fetch(baseUrl + "/events", {
  method: "POST", headers,
  body: JSON.stringify({ user_id: tid, event_name: "submission_created", payload: { file_id: fileId, package: pkg } })
});

const delayH = appConfig.AUTO_APPROVE_DELAY_HOURS || 1;
const text = "Фото получено!\\n\\nЗаявка будет одобрена автоматически через " + delayH + " час. Бонусы придут после одобрения.";

return [{ json: { ...input, replyText: text, crm: {...crm, state: "pending_approval", purchase_status: "pending"} } }];"""

# ==========================================
# Helper: make a branch pair (code + telegram)
# ==========================================
def make_branch(idx, code_name, code, tg_name, pos_y):
    code_node = {
        "id": f"br{idx}-code",
        "name": code_name,
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [880, pos_y],
        "parameters": {"jsCode": code}
    }
    tg_node = {
        "id": f"br{idx}-tg",
        "name": tg_name,
        "type": "n8n-nodes-base.telegram",
        "typeVersion": 1,
        "position": [1100, pos_y],
        "parameters": {
            "text": "={{ $json.replyText }}",
            "additionalFields": {"reply_markup": "={{ $json.replyKeyboard }}"}
        },
        "credentials": {"telegramApi": {"id": "b1x5cXjr8PBaOxPy", "name": "CH-SPA Bot Token"}}
    }
    return code_node, tg_node

# Build all branch nodes
branches_data = [
    (0, "Start Welcome", b0_code, "Send Start Welcome", 200),
    (1, "Check Subscription", b1_code, "Send Check Sub", 320),
    (2, "Sub Confirmed", b2_code, "Send Contact Request", 440),
    (3, "Save Contact", b3_code, "Send Package Choice", 560),
    (7, "Save Photo V2", b7_code, "Send Photo Received", 680),
]

all_new = []
branch_names_to_idx = {}

for idx, code_name, code, tg_name, pos_y in branches_data:
    c_node, t_node = make_branch(idx, code_name, code, tg_name, pos_y)
    all_new.append(c_node)
    all_new.append(t_node)
    branch_names_to_idx[code_name] = idx

# Get existing workflow
resp = s.get(f"{BASE}/rest/workflows/{V2_ID}")
wf = resp.json().get('data', resp.json())
existing = wf.get('nodes', [])

# Remove Supabase Call (we use direct fetch)
all_nodes = [n for n in existing if n['name'] != 'Supabase Call']
all_nodes.extend(all_new)

# Build connections
conns = {
    "Telegram Trigger": {"main": [[{"node": "App Config", "type": "main", "index": 0}]]},
    "App Config": {"main": [[{"node": "Upsert User", "type": "main", "index": 0}]]},
    "Upsert User": {"main": [[{"node": "Router", "type": "main", "index": 0}]]},
}

# Router -> each branch
router_branches = []
for idx, code_name, _, tg_name, _ in branches_data:
    router_branches.append([
        {"node": code_name, "type": "main", "index": 0}
    ])
    # Code node -> Telegram node
    conns[code_name] = {"main": [[{"node": tg_name, "type": "main", "index": 0}]]}

conns["Router"] = {"main": router_branches}

# Upload
resp = s.patch(f"{BASE}/rest/workflows/{V2_ID}", json={
    "nodes": all_nodes,
    "connections": conns,
    "settings": {"timezone": "Europe/Moscow"}
})

print(f"V2 update: {resp.status_code}")
if resp.ok:
    result = resp.json().get('data', resp.json())
    print(f"Nodes: {len(result.get('nodes', []))}")
    for n in result.get('nodes', []):
        print(f"  {n['name']} ({n['type'].split('.')[-1]})")
    print(f"Connections: {len(result.get('connections', {}))}")
    print(f"\nOpen: {BASE}/workflow/{V2_ID}")
else:
    print(f"Error: {resp.text[:500]}")

s.close()
