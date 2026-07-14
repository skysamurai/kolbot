import requests, sys
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)
V2_ID = 'oV8dWIoAUHRkLaSb'

r = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf = r.json().get('data', r.json())
nodes = wf.get('nodes', [])

# Remove Prepare Offset
nodes = [n for n in nodes if n.get('name') != 'Prepare Offset']

# Fix Fetch Updates URL - no expressions
for node in nodes:
    if node.get('name') == 'Fetch Updates':
        node['parameters']['url'] = 'https://api.telegram.org/bot8589709724:AAF8R-tki276jyAw69b1EhAEm2hp-5E2j_I/getUpdates?timeout=2&limit=1'
        print('Fixed Fetch Updates URL')

# Simplify Process Updates
simpler_code = 'const data = $input.first().json;\nif (!data.ok || !data.result || data.result.length === 0) {\n  return [];\n}\nconst results = [];\nfor (const update of data.result) {\n  results.push({json: update});\n}\nreturn results;'

for node in nodes:
    if node.get('name') == 'Process Updates':
        node['parameters']['jsCode'] = simpler_code
        print('Simplified Process Updates')

# Update connections
conns = wf.get('connections', {})
conns['Polling Cron'] = {'main': [[{'node': 'Fetch Updates', 'type': 'main', 'index': 0}]]}
conns.pop('Prepare Offset', None)

r2 = s.patch(f'{BASE}/rest/workflows/{V2_ID}', json={'nodes': nodes, 'connections': conns})
print(f'Update: {r2.status_code}')
if not r2.ok:
    print('Error:', r2.text[:500])
    sys.exit(1)

# Reactivate
r3 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf2 = r3.json().get('data', r3.json())
version_id = wf2.get('versionId')
r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': version_id}, timeout=60)
print(f'Activate: {r4.status_code}')
if r4.ok:
    print('Active!')
else:
    print('Error:', r4.json().get('message', r4.text)[:500])
s.close()
