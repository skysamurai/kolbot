"""Revert Start Welcome to working state and fix keyboard as JSON STRING (not object)"""
import requests, sys, json
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)
V2_ID = 'oV8dWIoAUHRkLaSb'

s.post(f'{BASE}/rest/workflows/{V2_ID}/deactivate', timeout=30)

r = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf = r.json().get('data', r.json())
nodes = wf.get('nodes', [])
conns = wf.get('connections', {})

# Revert Start Welcome Code node to working version
# Key fix: replyKeyboard output as JSON STRING (not object)
reverted_code = '''// ROUTE GATE: only process if _route === 0
if ($input.first().json._route !== 0) { return []; }

const input = $input.first().json;
const _n8nThis = this;

async function fetch(url, opts) {
  opts = opts || {};
  const options = {
    url: url,
    method: opts.method || 'GET',
    headers: opts.headers || {}
  };
  if (opts.body) {
    try { options.body = JSON.parse(opts.body); } catch(e) { options.body = opts.body; }
  }
  const result = await _n8nThis.helpers.httpRequest(options);
  return {
    status: 200,
    ok: true,
    json: async function() { return result; },
    text: async function() { return JSON.stringify(result); }
  };
}

const crm = input.crm || {};
const firstName = crm.first_name || "";
const appConfig = input.app_config;
const baseUrl = appConfig.SUPABASE_REST_URL;
const apiKey = appConfig.SUPABASE_SERVICE_ROLE_KEY;
const headers = {"apikey": apiKey, "Authorization": "Bearer " + apiKey, "Content-Type": "application/json"};
const tid = crm.telegram_id;

await fetch(baseUrl + "/rest/v1/users?telegram_id=eq." + tid, {
  method: "PATCH", headers,
  body: JSON.stringify({ user_state: "new", last_seen: new Date().toISOString() })
});
await fetch(baseUrl + "/rest/v1/events", {
  method: "POST", headers,
  body: JSON.stringify({ user_id: tid, event_name: "start", payload: {} })
});

const text = "Привет" + (firstName ? ", " + firstName : "") + "!\\nДобро пожаловать в CH-SPA!\\n\\nПодпишитесь на наш канал и нажмите Проверить подписку чтобы получить бонусы.";

// Output replyKeyboard as JSON STRING (what Telegram node expects)
const kb = JSON.stringify({"inline_keyboard": [[{"text": "Проверить подписку", "callback_data": "SUB_CONFIRMED"}]]});

return [{ json: { ...input, replyText: text, replyKeyboard: kb, crm: {...crm, state: "awaiting_subscription"} } }];
'''

for node in nodes:
    if node.get('name') == 'Start Welcome' and node.get('type') == 'n8n-nodes-base.code':
        node['parameters']['jsCode'] = reverted_code
        print('Reverted Start Welcome Code node')
        break

# Restore Start Welcome -> Send Start Welcome connection
conns['Start Welcome'] = {
    'main': [[{'node': 'Send Start Welcome', 'type': 'main', 'index': 0}]]
}
print('Restored connection: Start Welcome -> Send Start Welcome')

# Fix Send Start Welcome: use expression for reply_markup
for node in nodes:
    if node.get('name') == 'Send Start Welcome':
        params = node.get('parameters', {})
        # Change from hardcoded JSON string to expression
        af = params.get('additionalFields', {})
        af['reply_markup'] = '={{ $json.replyKeyboard }}'
        params['additionalFields'] = af
        print('Fixed Send Start Welcome: reply_markup = expression')
        break

# Upload
r2 = s.patch(f'{BASE}/rest/workflows/{V2_ID}', json={'nodes': nodes, 'connections': conns})
print(f'Update: {r2.status_code}')
if not r2.ok:
    print('Error:', r2.text[:500])
    sys.exit(1)

# Verify
r3 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf2 = r3.json().get('data', r3.json())
for n in wf2.get('nodes', []):
    if n.get('name') == 'Start Welcome':
        code = n.get('parameters', {}).get('jsCode', '')
        has_stringify = 'JSON.stringify' in code
        has_send = 'sendTelegram' in code or 'tgResponse' in code
        print(f'VERIFIED: JSON.stringify={has_stringify}, has_direct_send={has_send}')
    if n.get('name') == 'Send Start Welcome':
        rm = n.get('parameters', {}).get('additionalFields', {}).get('reply_markup', '')
        print(f'VERIFIED: reply_markup = {rm}')

# Activate
v = wf2.get('versionId')
r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': v}, timeout=60)
print(f'Activate: {r4.status_code}')
if not r4.ok:
    print('Error:', r4.json().get('message', r4.text)[:500])

s.close()
