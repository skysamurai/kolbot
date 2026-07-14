import requests, json, sys
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'})
V2_ID = 'oV8dWIoAUHRkLaSb'

# Get workflow
r = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf = r.json().get('data', r.json())
nodes = wf.get('nodes', [])
conns = wf.get('connections', {})

# 1. Remove Telegram Trigger
nodes = [n for n in nodes if n.get('name') != 'Telegram Trigger']

# 2. Add Cron trigger (every 3 sec)
cron = {
    'id': 'poll-cron-v2',
    'name': 'Polling Cron',
    'type': 'n8n-nodes-base.scheduleTrigger',
    'typeVersion': 1,
    'position': [0, 300],
    'parameters': {
        'rule': {
            'interval': [{'field': 'seconds', 'secondsInterval': 3}]
        }
    }
}
nodes.append(cron)

# 3. Code node to prepare offset
prep_code = """const wfData = $getWorkflowStaticData('global');
const offset = wfData.telegramOffset || 0;
return [{json: {offset: offset}}];"""

prep_node = {
    'id': 'poll-prep-v2',
    'name': 'Prepare Offset',
    'type': 'n8n-nodes-base.code',
    'typeVersion': 2,
    'position': [220, 300],
    'parameters': {'jsCode': prep_code}
}
nodes.append(prep_node)

# 4. HTTP Request node - uses offset from Prepare Offset
http_node = {
    'id': 'poll-http-v2',
    'name': 'Fetch Updates',
    'type': 'n8n-nodes-base.httpRequest',
    'typeVersion': 3,
    'position': [440, 300],
    'parameters': {
        'method': 'GET',
        'url': '=https://api.telegram.org/bot8589709724:AAF8R-tki276jyAw69b1EhAEm2hp-5E2j_I/getUpdates?timeout=2&limit=1&offset={{ $json.offset }}',
        'options': {
            'response': {
                'response': {
                    'responseFormat': 'json'
                }
            }
        }
    }
}
nodes.append(http_node)

# 5. Code node to process results and update offset
process_code = """const data = $input.first().json;
if (!data.ok || !data.result || data.result.length === 0) {
  return [{json: {no_updates: true}}];
}

const wfData = $getWorkflowStaticData('global');
const results = [];

for (const update of data.result) {
  wfData.telegramOffset = update.update_id + 1;
  results.push({json: update});
}

return results;"""

process_node = {
    'id': 'poll-process-v2',
    'name': 'Process Updates',
    'type': 'n8n-nodes-base.code',
    'typeVersion': 2,
    'position': [660, 300],
    'parameters': {'jsCode': process_code}
}
nodes.append(process_node)

# 6. Wire connections
conns.pop('Telegram Trigger', None)
conns['Polling Cron'] = {'main': [[{'node': 'Prepare Offset', 'type': 'main', 'index': 0}]]}
conns['Prepare Offset'] = {'main': [[{'node': 'Fetch Updates', 'type': 'main', 'index': 0}]]}
conns['Fetch Updates'] = {'main': [[{'node': 'Process Updates', 'type': 'main', 'index': 0}]]}
conns['Process Updates'] = {'main': [[{'node': 'App Config', 'type': 'main', 'index': 0}]]}

# Upload
r2 = s.patch(f'{BASE}/rest/workflows/{V2_ID}', json={'nodes': nodes, 'connections': conns})
print(f'Update: {r2.status_code}')
if not r2.ok:
    print('Error:', r2.text[:500])
    sys.exit(1)

# Activate
r3 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf2 = r3.json().get('data', r3.json())
version_id = wf2.get('versionId')

r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': version_id}, timeout=60)
print(f'Activate: {r4.status_code}')
if r4.ok:
    print('*** WORKFLOW ACTIVATED ***')
else:
    err = r4.json()
    print('Error:', err.get('message', r4.text)[:500])

s.close()
