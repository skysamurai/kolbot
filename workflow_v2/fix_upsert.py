import requests, sys
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)
V2_ID = 'oV8dWIoAUHRkLaSb'

r = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf = r.json().get('data', r.json())
nodes = wf.get('nodes', [])

# Complete rewrite of Upsert User with polyfill and proper $input
upsert_code = '''const _n8nThis = this;

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

const input = $input.first().json;
const appConfig = input.app_config || {};
const baseUrl = appConfig.SUPABASE_REST_URL;
const apiKey  = appConfig.SUPABASE_SERVICE_ROLE_KEY;

const headers = {
  apikey: apiKey,
  Authorization: 'Bearer ' + apiKey,
  'Content-Type': 'application/json',
  Prefer: 'return=representation'
};

const msg = input.message || {};
const cb  = input.callback_query || {};
const from = msg.from || cb.from || {};
const telegramId = String(from.id || '');
const username   = from.username || '';
const firstName  = from.first_name || '';
const lastName   = from.last_name || '';

if (!telegramId) {
  return [{ json: { error: 'No telegram_id', crm: { state: 'new' } } }];
}

let user = null;
const getUrl = baseUrl + '/users?telegram_id=eq.' + telegramId + '&select=*';
const getResp = await fetch(getUrl, { headers: headers });
const getData = await getResp.json();
user = Array.isArray(getData) ? getData[0] : getData;

const now = new Date().toISOString();

if (user) {
  await fetch(baseUrl + '/users?telegram_id=eq.' + telegramId, {
    method: 'PATCH',
    headers: headers,
    body: JSON.stringify({ last_seen: now })
  });
} else {
  const createResp = await fetch(baseUrl + '/users', {
    method: 'POST',
    headers: headers,
    body: JSON.stringify({
      telegram_id: telegramId,
      username: username,
      first_name: firstName,
      last_name: lastName,
      user_state: 'new',
      bonus_access: 'locked',
      last_seen: now
    })
  });
  const createData = await createResp.json();
  user = Array.isArray(createData) ? createData[0] : createData;
}

const crm = {
  telegram_id: telegramId,
  state: user ? (user.user_state || 'new') : 'new',
  purchase_status: user ? (user.purchase_status || null) : null,
  bonus_access: user ? (user.bonus_access || 'locked') : 'locked',
  selected_package: user ? (user.selected_package || null) : null,
  phone: user ? (user.phone || null) : null,
  username: username,
  first_name: firstName
};

return [{
  json: Object.assign({}, input, { crm: crm, user: user, telegram_id: telegramId, raw: input.raw || input })
}];'''

for node in nodes:
    if node.get('name') == 'Upsert User':
        node['parameters']['jsCode'] = upsert_code
        print('Upsert User rewritten with $input preserved')

r2 = s.patch(f'{BASE}/rest/workflows/{V2_ID}', json={'nodes': nodes})
print(f'Update: {r2.status_code}')

# Verify
r3 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf2 = r3.json().get('data', r3.json())
for n in wf2.get('nodes', []):
    if n.get('name') == 'Upsert User':
        code = n.get('parameters', {}).get('jsCode', '')
        if '$input' in code:
            print('VERIFIED: $input present')
        if '_n8nThis' in code:
            print('VERIFIED: polyfill present')
        break

version_id = wf2.get('versionId')
r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': version_id}, timeout=60)
print(f'Activate: {r4.status_code}')
s.close()
