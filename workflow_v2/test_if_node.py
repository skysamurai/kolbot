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

# Replace Router Switch with an IF node for testing
for node in nodes:
    if node.get('name') == 'Router':
        node['type'] = 'n8n-nodes-base.if'
        node['typeVersion'] = 2
        node['parameters'] = {
            "conditions": {
                "options": {
                    "caseSensitive": True,
                    "leftValue": "",
                    "operator": "=",
                    "typeValidation": "strict",
                    "version": 2
                },
                "conditions": [
                    {
                        "id": "test-condition",
                        "leftValue": "={{ $json._route }}",
                        "rightValue": 0,
                        "operator": "="
                    }
                ],
                "combinator": "and"
            }
        }
        print('Router converted to IF node (test)')

# Fix connections: IF node has true/false outputs, not 26
# Put all downstream nodes on the 'true' output
router_conns = conns.get('Router', {}).get('main', [])
all_targets = []
for output_group in router_conns:
    for target in output_group:
        if target not in all_targets:
            all_targets.append(target)
# IF node outputs: [true_targets, false_targets]
conns['Router'] = {'main': [all_targets, []]}
print(f'IF: {len(all_targets)} nodes on true, none on false')

r2 = s.patch(f'{BASE}/rest/workflows/{V2_ID}', json={'nodes': nodes, 'connections': conns})
print(f'Update: {r2.status_code}')
if not r2.ok:
    print('Error:', r2.text[:500])
    sys.exit(1)

r3 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf2 = r3.json().get('data', r3.json())
version_id = wf2.get('versionId')
r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': version_id}, timeout=60)
print(f'Activate: {r4.status_code}')
if not r4.ok:
    print('Error:', r4.json().get('message', r4.text)[:500])

time.sleep(8)

r5 = s.get(f'{BASE}/rest/executions?workflowId={V2_ID}&limit=3')
results = r5.json().get('data', {}).get('results', [])
for ex in results[:3]:
    eid = ex['id']
    r6 = s.get(f'{BASE}/rest/executions/{eid}')
    raw = r6.text
    started = ex.get('startedAt', '')[:19]
    if 'Cannot read properties' in raw:
        print(f'{started} | {ex["status"]:10} | CRASH')
    else:
        print(f'{started} | {ex["status"]:10} | OK')
s.close()
