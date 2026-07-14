"""Восстановить Start Welcome код и добавить диагностику"""
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

# Восстановить Start Welcome
start_welcome_code = '''// ROUTE GATE: only process if _route === 0
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

console.log('START_WELCOME: вход. _route=' + $input.first().json._route);

const crm = input.crm || {};
const firstName = crm.first_name || "";
const appConfig = input.app_config;
const baseUrl = appConfig.SUPABASE_REST_URL;
const apiKey = appConfig.SUPABASE_SERVICE_ROLE_KEY;
const headers = {"apikey": apiKey, "Authorization": "Bearer " + apiKey, "Content-Type": "application/json"};
const tid = crm.telegram_id;

console.log('START_WELCOME: telegram_id=' + tid + ' firstName=' + firstName);

try {
  await fetch(baseUrl + "/rest/v1/users?telegram_id=eq." + tid, {
    method: "PATCH", headers,
    body: JSON.stringify({ user_state: "new", last_seen: new Date().toISOString() })
  });
  console.log('START_WELCOME: users PATCH OK');
} catch(e) {
  console.log('START_WELCOME: users PATCH error: ' + e.message);
}

try {
  await fetch(baseUrl + "/rest/v1/events", {
    method: "POST", headers,
    body: JSON.stringify({ user_id: tid, event_name: "start", payload: {} })
  });
  console.log('START_WELCOME: events POST OK');
} catch(e) {
  console.log('START_WELCOME: events POST error: ' + e.message);
}

const text = "Привет" + (firstName ? ", " + firstName : "") + "!\\nДобро пожаловать в CH-SPA!\\n\\nПодпишитесь на наш канал и нажмите Проверить подписку чтобы получить бонусы.";

// Выводим replyKeyboard как JSON-строку для Telegram ноды
const kb = JSON.stringify({"inline_keyboard": [[{"text": "Проверить подписку", "callback_data": "SUB_CONFIRMED"}]]});

console.log('START_WELCOME: отправляю ответ. chatId=' + ((input.message || input.callback_query.message).chat.id));

return [{ json: { ...input, replyText: text, replyKeyboard: kb, crm: {...crm, state: "awaiting_subscription"} } }];
'''

fixed_start = False
for node in nodes:
    if node.get('name') == 'Start Welcome':
        node['parameters'] = {
            'mode': 'runOnceForAllItems',
            'language': 'javascript',
            'jsCode': start_welcome_code
        }
        fixed_start = True
        print('Start Welcome код восстановлен с диагностикой')
        break

if not fixed_start:
    print('ERROR: Start Welcome не найден')
    sys.exit(1)

# Также добавим лог в Upsert User
for node in nodes:
    if node.get('name') == 'Upsert User':
        code = node.get('parameters', {}).get('jsCode', '')
        if 'console.log' not in code:
            # Добавим лог после получения input
            code = code.replace(
                'const input = $input.first().json;',
                'const input = $input.first().json;\nconsole.log("UPSERT_USER: input получен, ключи: " + JSON.stringify(Object.keys(input)).substring(0,200));'
            )
            node['parameters']['jsCode'] = code
            print('Upsert User: добавлен console.log')
        break

# Upload
r2 = s.patch(f'{BASE}/rest/workflows/{V2_ID}', json={'nodes': nodes})
print(f'Update: {r2.status_code}')
if not r2.ok:
    print('Error:', r2.text[:500])
    sys.exit(1)

# Activate
r3 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf2 = r3.json().get('data', r3.json())
v = wf2.get('versionId')
r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': v}, timeout=60)
print(f'Activate: {r4.status_code}')
if not r4.ok:
    print('Error:', r4.json().get('message', r4.text)[:500])
else:
    print('ГОТОВО! Отправь /start боту.')

s.close()
