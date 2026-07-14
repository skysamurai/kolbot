import requests, json

BASE = "https://n8n.ch-spa.com.ru"
s = requests.Session()
s.post(f"{BASE}/rest/login", json={"emailOrLdapLoginId": "shat.pomoshnik@gmail.com", "password": "1234Ko4321"})

V2_ID = "oV8dWIoAUHRkLaSb"

# Package lookup helper (shared pattern)
pkg_header = """const input = $input.first().json;
const crm = input.crm || {};
const appConfig = input.app_config;
const baseUrl = appConfig.SUPABASE_REST_URL;
const apiKey = appConfig.SUPABASE_SERVICE_ROLE_KEY;
const headers = {"apikey": apiKey, "Authorization": "Bearer " + apiKey, "Content-Type": "application/json"};
const tid = crm.telegram_id;"""

# ==========================================
# Branches 4/5/6: Package Selection (unified)
# ==========================================
def pkg_code(pkg_key):
    return pkg_header + f"""
await fetch(baseUrl + "/users?telegram_id=eq." + tid, {{
  method: "PATCH", headers,
  body: JSON.stringify({{ selected_package: "{pkg_key}", user_state: "awaiting_photo", last_seen: new Date().toISOString() }})
}});
await fetch(baseUrl + "/events", {{
  method: "POST", headers,
  body: JSON.stringify({{ user_id: tid, event_name: "package_selected", payload: {{ package: "{pkg_key}" }} }})
}});

const text = "Вы выбрали {pkg_key}. Теперь загрузите фото чека.";
return [{{ json: {{ ...input, replyText: text, crm: {{...crm, state: "awaiting_photo", selected_package: "{pkg_key}"}} }} }}];"""

# ==========================================
# Branch 16: Status
# ==========================================
b16_code = pkg_header + """
const resp = await fetch(baseUrl + "/users?telegram_id=eq." + tid + "&select=user_state,selected_package,purchase_status,bonus_access");
const data = await resp.json();
const user = Array.isArray(data) ? data[0] : data;

let text = "Ваш статус:\\n";
text += "Состояние: " + (user?.user_state || "неизвестно") + "\\n";
if (user?.selected_package) text += "Пакет: " + user.selected_package + "\\n";
if (user?.purchase_status) text += "Заявка: " + user.purchase_status + "\\n";
text += "Бонусы: " + (user?.bonus_access === "unlocked" ? "доступны" : "заблокированы");

return [{ json: { ...input, replyText: text, crm } }];"""

# ==========================================
# Branch 17: Back
# ==========================================
b17_code = pkg_header + """
// Go back one step in the funnel
const state = crm.state;
let newState = "new";
if (state === "awaiting_contact") newState = "awaiting_subscription";
else if (state === "awaiting_package") newState = "awaiting_contact";
else if (state === "awaiting_photo") newState = "awaiting_package";
else if (state === "pending_approval") newState = "awaiting_photo";
else if (state.startsWith("awaiting_review")) newState = "approved";

await fetch(baseUrl + "/users?telegram_id=eq." + tid, {
  method: "PATCH", headers,
  body: JSON.stringify({ user_state: newState, last_seen: new Date().toISOString() })
});

return [{ json: { ...input, replyText: "Возвращаемся назад...", crm: {...crm, state: newState} } }];"""

# ==========================================
# Branch 18: Continue
# ==========================================
b18_code = pkg_header + """
return [{ json: { ...input, replyText: "Продолжаем!", crm } }];"""

# ==========================================
# Branch 19: Reset
# ==========================================
b19_code = pkg_header + """
await fetch(baseUrl + "/users?telegram_id=eq." + tid, {
  method: "PATCH", headers,
  body: JSON.stringify({ user_state: "new", purchase_status: null, bonus_access: "locked", selected_package: null, last_seen: new Date().toISOString() })
});
await fetch(baseUrl + "/events", {
  method: "POST", headers,
  body: JSON.stringify({ user_id: tid, event_name: "reset", payload: {} })
});

const text = "Всё сброшено! Начните заново с /start";
return [{ json: { ...input, replyText: text, crm: {...crm, state: "new", purchase_status: null, bonus_access: "locked"} } }];"""

# ==========================================
# Branch 20: Help
# ==========================================
b20_code = """const input = $input.first().json;
const text = "Чат-поддержка: @ch_spa_support\\n\\nКоманды:\\n/start - начать\\n/status - мой статус\\n/help - помощь\\n/back - назад\\n/continue - продолжить\\n/reset - начать заново";
return [{ json: { ...input, replyText: text } }];"""

# ==========================================
# Branch 25: Phone as text
# ==========================================
b25_code = pkg_header + """
const textMsg = input.message?.text || "";
const phoneLike = /^\\+?\\d[\\d\\s\\-()]{8,}$/.test(textMsg);
if (!phoneLike) {
  return [{ json: { ...input, replyText: "Пожалуйста, поделитесь контактом через кнопку ниже.", crm } }];
}
await fetch(baseUrl + "/users?telegram_id=eq." + tid, {
  method: "PATCH", headers,
  body: JSON.stringify({ phone: textMsg, user_state: "awaiting_package", last_seen: new Date().toISOString() })
});
const text = "Телефон сохранён. Выберите ваш набор бонусов:";
const kb = '{"inline_keyboard":[[{"text":"1 варежка (3000 руб.)","callback_data":"PACKAGE_STANDARD"}],[{"text":"1+2 варежки (7000 руб.)","callback_data":"PACKAGE_PREMIUM"}],[{"text":"VIP: 1+2+5 варежек (11000 руб.)","callback_data":"PACKAGE_VIP"}]]}';
return [{ json: { ...input, replyText: text, replyKeyboard: kb, crm: {...crm, state: "awaiting_package"} } }];"""

# Build all
def make_code(idx, name, code, pos_y):
    return {
        "id": f"br{idx}-code",
        "name": name,
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [880, pos_y],
        "parameters": {"jsCode": code}
    }

def make_tg(idx, name, pos_y):
    return {
        "id": f"br{idx}-tg",
        "name": name,
        "type": "n8n-nodes-base.telegram",
        "typeVersion": 1,
        "position": [1100, pos_y],
        "parameters": {
            "text": "={{ $json.replyText }}",
            "additionalFields": {"reply_markup": "={{ $json.replyKeyboard || '' }}"}
        },
        "credentials": {"telegramApi": {"id": "b1x5cXjr8PBaOxPy", "name": "CH-SPA Bot Token"}}
    }

new_branches = [
    (4, "Save Package Standard", pkg_code("standard"), "Send Pkg Standard", 800),
    (5, "Save Package Premium", pkg_code("premium"), "Send Pkg Premium", 920),
    (6, "Save Package VIP", pkg_code("vip"), "Send Pkg VIP", 1040),
    (16, "Build Status", b16_code, "Send Status", 1160),
    (17, "Build Back", b17_code, "Send Back", 1280),
    (18, "Build Continue", b18_code, "Send Continue", 1400),
    (19, "Reset State", b19_code, "Send Reset", 1520),
    (20, "Help Message", b20_code, "Send Help", 1640),
    (25, "Phone As Text", b25_code, "Send Phone Confirm", 1760),
]

all_new = []
router_branches = []

for br_idx, code_name, code, tg_name, pos_y in new_branches:
    c = make_code(br_idx, code_name, code, pos_y)
    t = make_tg(br_idx, tg_name, pos_y)
    all_new.append(c)
    all_new.append(t)
    router_branches.append((br_idx, code_name, tg_name))

# Get existing workflow
resp = s.get(f"{BASE}/rest/workflows/{V2_ID}")
wf = resp.json().get('data', resp.json())
existing_nodes = wf.get('nodes', [])
existing_conns = wf.get('connections', {})

# Merge nodes
all_nodes = existing_nodes + all_new

# Update Router connections - add new branches at correct indices
router_conns = existing_conns.get("Router", {}).get("main", [[] for _ in range(26)])

# Ensure we have 26 slots
while len(router_conns) < 26:
    router_conns.append([])

for br_idx, code_name, tg_name in router_branches:
    router_conns[br_idx] = [{"node": code_name, "type": "main", "index": 0}]
    existing_conns[code_name] = {"main": [[{"node": tg_name, "type": "main", "index": 0}]]}

existing_conns["Router"] = {"main": router_conns}

# Upload
resp = s.patch(f"{BASE}/rest/workflows/{V2_ID}", json={
    "nodes": all_nodes,
    "connections": existing_conns
})

print(f"Update: {resp.status_code}")
if resp.ok:
    result = resp.json().get('data', resp.json())
    print(f"Total nodes: {len(result.get('nodes', []))}")
    for n in result['nodes']:
        print(f"  {n['name']}")
else:
    print(f"Error: {resp.text[:400]}")

s.close()
