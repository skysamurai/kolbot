import requests, sys, time
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)
V2_ID = 'oV8dWIoAUHRkLaSb'

s.post(f'{BASE}/rest/workflows/{V2_ID}/deactivate', timeout=30)

r = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf = r.json().get('data', r.json())
nodes = wf.get('nodes', [])

# Test: hardcoded expression, always returns 0
for node in nodes:
    if node.get('name') == 'Router':
        node['parameters'] = {
            "mode": "expression",
            "numberOutputs": 2,
            "output": "0"
        }

r2 = s.patch(f'{BASE}/rest/workflows/{V2_ID}', json={'nodes': nodes})
print(f'Update: {r2.status_code}')

r3 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf2 = r3.json().get('data', r3.json())
version_id = wf2.get('versionId')
r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': version_id}, timeout=60)
print(f'Activate: {r4.status_code}')

time.sleep(10)

r5 = s.get(f'{BASE}/rest/executions?workflowId={V2_ID}&limit=5')
results = r5.json().get('data', {}).get('results', [])
for ex in results[:5]:
    status = ex.get('status')
    eid = ex['id']
    r6 = s.get(f'{BASE}/rest/executions/{eid}')
    raw = r6.text
    started = ex.get('startedAt', '')[:19]
    if 'Cannot read properties' in raw:
        has_crash = True
    else:
        has_crash = False
    print(f'{started} | {status:10} | Switch crash: {has_crash}')
s.close()
