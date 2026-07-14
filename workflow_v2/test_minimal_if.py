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
conns = wf.get('connections', {})

# Replace Router with IF, connect ONLY Start Welcome on true
for node in nodes:
    if node.get('name') == 'Router':
        node['type'] = 'n8n-nodes-base.if'
        node['typeVersion'] = 2
        node['parameters'] = {
            "conditions": {
                "options": {
                    "caseSensitive": True,
                    "leftValue": "",
                    "operator": "numberEquals",
                    "typeValidation": "strict",
                    "version": 2
                },
                "conditions": [
                    {
                        "id": "route-0",
                        "leftValue": "={{ $json._route }}",
                        "rightValue": 0,
                        "operator": "numberEquals"
                    }
                ],
                "combinator": "and"
            }
        }
        print('Router -> IF node, checking _route === 0')

# Connect only Start Welcome on true, nothing on false
conns['Router'] = {
    'main': [
        [{'node': 'Start Welcome', 'type': 'main', 'index': 0}],  # true
        []  # false
    ]
}
print('Only Start Welcome on IF true output')

r2 = s.patch(f'{BASE}/rest/workflows/{V2_ID}', json={'nodes': nodes, 'connections': conns})
print(f'Update: {r2.status_code}')
if not r2.ok:
    print('Error:', r2.text[:300])

r3 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf2 = r3.json().get('data', r3.json())
version_id = wf2.get('versionId')
r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': version_id}, timeout=60)
print(f'Activate: {r4.status_code}')
if not r4.ok:
    err = r4.json().get('message', '')
    print(f'Error: {err[:300]}')

time.sleep(15)

r5 = s.get(f'{BASE}/rest/executions?workflowId={V2_ID}&limit=5')
results = r5.json().get('data', {}).get('results', [])
for ex in results[:5]:
    eid = ex['id']
    r6 = s.get(f'{BASE}/rest/executions/{eid}')
    raw = r6.text
    started = ex.get('startedAt', '')[:19]
    status = ex.get('status')
    
    # Check for specific errors
    if 'Cannot read properties of undefined' in raw and 'toLowerCase' in raw:
        print(f'{started} | {status:10} | IF: toLowerCase error')
    elif 'Cannot read properties of undefined' in raw and 'push' in raw:
        print(f'{started} | {status:10} | IF: push error')
    elif 'is not defined' in raw:
        import re
        m = re.search(r'(\w+ is not defined)', raw)
        err = m.group(1) if m else 'unknown'
        print(f'{started} | {status:10} | {err}')
    else:
        print(f'{started} | {status:10} | other/ok')
s.close()
