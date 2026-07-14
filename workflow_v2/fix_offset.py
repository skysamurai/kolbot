import requests, sys
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

# Step 1: Add a "Prepare URL" Code node BEFORE Fetch Updates
prepare_url_code = """// Prepare Telegram getUpdates URL with offset tracking
const offset = $getWorkflowStaticData('global').telegram_offset || 0;
const botToken = '8589709724:AAF8R-tki276jyAw69b1EhAEm2hp-5E2j_I';
const url = 'https://api.telegram.org/bot' + botToken + '/getUpdates?timeout=2&limit=1&offset=' + offset;
return [{json: {url: url, offset: offset}}];"""

prepare_node = {
    'id': 'prepare-url',
    'name': 'Prepare URL',
    'type': 'n8n-nodes-base.code',
    'typeVersion': 1,
    'position': [260, 300],
    'parameters': {
        'mode': 'runOnceForAllItems',
        'language': 'javascript',
        'jsCode': prepare_url_code
    }
}
nodes.append(prepare_node)

# Step 2: Fix Fetch Updates URL to use $json.url from Prepare URL
for node in nodes:
    if node.get('name') == 'Fetch Updates':
        node['parameters']['url'] = '={{ $json.url }}'
        print('Fixed Fetch Updates: URL from Prepare URL node')

# Step 3: Fix Process Updates to track offset
process_code = """// Process Telegram getUpdates response and track offset
const data = $input.first().json;

if (!data.ok || !data.result || data.result.length === 0) {
  return [];
}

const results = [];
let maxUpdateId = $getWorkflowStaticData('global').telegram_offset || 0;

for (const update of data.result) {
  results.push({json: update});
  if (update.update_id > maxUpdateId) {
    maxUpdateId = update.update_id;
  }
}

// Store next offset to acknowledge processed updates
$getWorkflowStaticData('global').telegram_offset = maxUpdateId + 1;

return results;"""

for node in nodes:
    if node.get('name') == 'Process Updates':
        node['parameters']['jsCode'] = process_code
        print('Fixed Process Updates: offset tracking')

# Step 4: Fix connections
# Polling Cron -> Prepare URL -> Fetch Updates -> Process Updates -> ...
conns['Polling Cron'] = {'main': [[{'node': 'Prepare URL', 'type': 'main', 'index': 0}]]}
conns['Prepare URL'] = {'main': [[{'node': 'Fetch Updates', 'type': 'main', 'index': 0}]]}
# Fetch Updates -> Process Updates and Process Updates -> App Config should already be set

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
    name = n.get('name', '')
    if name == 'Prepare URL':
        code = n.get('parameters', {}).get('jsCode', '')
        if '$getWorkflowStaticData' in code:
            print('VERIFIED: Prepare URL uses static data')
    if name == 'Fetch Updates':
        url = n.get('parameters', {}).get('url', '')
        print(f'VERIFIED: Fetch Updates URL = {url}')
    if name == 'Process Updates':
        code = n.get('parameters', {}).get('jsCode', '')
        if 'telegram_offset' in code:
            print('VERIFIED: Process Updates tracks offset')

v = wf2.get('versionId')
r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': v}, timeout=60)
print(f'Activate: {r4.status_code}')
if not r4.ok:
    print('Error:', r4.json().get('message', r4.text)[:500])

print(f'Total nodes: {len(wf2.get("nodes", []))}')
s.close()
