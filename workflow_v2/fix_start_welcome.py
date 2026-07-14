"""Fix Start Welcome: send Telegram message with keyboard via httpRequest (proxy-safe)"""
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

BOT_TOKEN = '8589709724:AAF8R-tki276jyAw69b1EhAEm2hp-5E2j_I'

new_code = '''// ROUTE GATE: only process if _route === 0
if ($input.first().json._route !== 0) { return []; }

const input = $input.first().json;
const _n8nThis = this;

// Polyfill fetch using n8n httpRequest (respects HTTP_PROXY for Telegram API access)
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
  return { status: 200, ok: true, json: async function() { return result; }, text: async function() { return JSON.stringify(result); } };
}

const BOT_TOKEN = 'BOT_TOKEN_PLACEHOLDER';

// Check subscription status and return user data
const crm = input.crm || {};
const firstName = crm.first_name || '';
const appConfig = input.app_config;
const baseUrl = appConfig.SUPABASE_REST_URL;
const apiKey = appConfig.SUPABASE_SERVICE_ROLE_KEY;
const headers = {
  'apikey': apiKey,
  'Authorization': 'Bearer ' + apiKey,
  'Content-Type': 'application/json'
};
const tid = crm.telegram_id;

// Update user state
await fetch(baseUrl + '/rest/v1/users?telegram_id=eq.' + tid, {
  method: 'PATCH', headers,
  body: JSON.stringify({ user_state: 'new', last_seen: new Date().toISOString() })
});

// Log event
await fetch(baseUrl + '/rest/v1/events', {
  method: 'POST', headers,
  body: JSON.stringify({ user_id: tid, event_name: 'start', payload: {} })
});

const text = 'Привет' + (firstName ? ', ' + firstName : '') + '!\\nДобро пожаловать в CH-SPA!\\n\\nПодпишитесь на наш канал и нажмите Проверить подписку чтобы получить бонусы.';
const kb = { inline_keyboard: [[{ text: 'Проверить подписку', callback_data: 'SUB_CONFIRMED' }]] };

// Send welcome message with keyboard directly via Telegram Bot API (through proxy)
const chatId = (input.message || input.callback_query.message).chat.id;
const tgResponse = await fetch('https://api.telegram.org/bot' + BOT_TOKEN + '/sendMessage', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    chat_id: chatId,
    text: text,
    reply_markup: kb
  })
});

console.log('Telegram sendMessage response:', JSON.stringify(await tgResponse.json()));

return [{ json: { ...input, replyText: text, replyKeyboard: kb, crm: { ...crm, state: 'awaiting_subscription' } } }];
'''.replace('BOT_TOKEN_PLACEHOLDER', BOT_TOKEN)

# Update Start Welcome Code node
found = False
for node in nodes:
    if node.get('name') == 'Start Welcome' and node.get('type') == 'n8n-nodes-base.code':
        node['parameters']['jsCode'] = new_code
        node['parameters']['mode'] = 'runOnceForAllItems'
        node['parameters']['language'] = 'javascript'
        found = True
        print('Updated Start Welcome Code node')
        break

if not found:
    print('ERROR: Start Welcome node not found!')
    sys.exit(1)

# Remove connection: Start Welcome -> Send Start Welcome (we send directly)
if 'Start Welcome' in conns:
    conns['Start Welcome'] = {'main': []}

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
        has_send = 'tgResponse' in code
        has_kb = 'inline_keyboard' in code
        has_chatId = 'input.message || input.callback_query' in code
        print(f'VERIFIED: sendMessage={has_send}, keyboard={has_kb}, chatId={has_chatId}')
        # Show the send part
        for line in code.split('\n'):
            if 'tgResponse' in line or 'sendMessage' in line:
                print(f'  {line.strip()[:150]}')
        break

# Activate
v = wf2.get('versionId')
r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': v}, timeout=60)
print(f'Activate: {r4.status_code}')
if not r4.ok:
    print('Error:', r4.json().get('message', r4.text)[:500])

s.close()
