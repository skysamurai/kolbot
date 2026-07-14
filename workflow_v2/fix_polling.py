import requests, json, sys
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'})
V2_ID = 'oV8dWIoAUHRkLaSb'

r = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf = r.json().get('data', r.json())
nodes = wf.get('nodes', [])
conns = wf.get('connections', {})

# Remove Telegram Trigger
nodes = [n for n in nodes if n.get('name') != 'Telegram Trigger']
print(f'Removed Telegram Trigger, {len(nodes)} nodes left')

# Add Polling Cron
poll_cron = {
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
nodes.append(poll_cron)

# Add Polling Worker
poll_code = (
    "const appConfig = $input.first().json.app_config || $input.first().json;\n"
    "const baseUrl = appConfig.SUPABASE_REST_URL;\n"
    "const apiKey = appConfig.SUPABASE_SERVICE_ROLE_KEY;\n"
    "const headers = {'apikey': apiKey, 'Authorization': 'Bearer ' + apiKey, 'Content-Type': 'application/json'};\n"
    "const botToken = appConfig.TELEGRAM_BOT_TOKEN;\n"
    "\n"
    "const workflowStaticData = $getWorkflowStaticData('global');\n"
    "let offset = workflowStaticData.telegramOffset || 0;\n"
    "\n"
    "const url = 'https://api.telegram.org/bot' + botToken + '/getUpdates?timeout=2&offset=' + (offset + 1);\n"
    "const resp = await fetch(url);\n"
    "const data = await resp.json();\n"
    "\n"
    "if (!data.ok || !data.result) {\n"
    "  return [{json: {no_updates: true}}];\n"
    "}\n"
    "\n"
    "const results = [];\n"
    "for (const update of data.result) {\n"
    "  if (update.update_id > offset) {\n"
    "    offset = update.update_id;\n"
    "  }\n"
    "  if (update.message) {\n"
    "    results.push({json: update});\n"
    "  } else if (update.callback_query) {\n"
    "    results.push({json: update});\n"
    "  }\n"
    "}\n"
    "\n"
    "workflowStaticData.telegramOffset = offset;\n"
    "\n"
    "if (results.length === 0) {\n"
    "  return [{json: {no_updates: true}}];\n"
    "}\n"
    "return results;"
)

poll_code_node = {
    'id': 'poll-code-v2',
    'name': 'Poll Telegram',
    'type': 'n8n-nodes-base.code',
    'typeVersion': 2,
    'position': [220, 300],
    'parameters': {'jsCode': poll_code}
}
nodes.append(poll_code_node)

# Update connections
if 'Telegram Trigger' in conns:
    del conns['Telegram Trigger']

conns['Polling Cron'] = {'main': [[{'node': 'Poll Telegram', 'type': 'main', 'index': 0}]]}
conns['Poll Telegram'] = {'main': [[{'node': 'App Config', 'type': 'main', 'index': 0}]]}

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

r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': version_id}, timeout=90)
print(f'Activate: {r4.status_code}')
if r4.ok:
    print('SUCCESS - Workflow activated!')
else:
    err = r4.json()
    print('Error:', err.get('message', r4.text)[:800])

s.close()
