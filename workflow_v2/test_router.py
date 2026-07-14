import requests, sys
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)
V2_ID = 'oV8dWIoAUHRkLaSb'

r = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf = r.json().get('data', r.json())
nodes = wf.get('nodes', [])
conns = wf.get('connections', {})

# Test: reduce Router to 2 outputs, connect everything to output 0
for node in nodes:
    if node.get('name') == 'Router':
        node['parameters'] = {
            "mode": "expression",
            "numberOutputs": 2,
            "output": "0"
        }
        print('Router: set to 2 outputs, always returns 0')

# Update all connections FROM Router to only reference output 0
# Router currently has 26 outputs connected to various nodes
# We need to move ALL to output 0 (or delete outputs 1-25)
router_conns = conns.get('Router', {}).get('main', [])
if router_conns:
    # Take all nodes that were on any output and put them on output 0
    all_targets = []
    for output_group in router_conns:
        for target in output_group:
            if target not in all_targets:
                all_targets.append(target)
    conns['Router'] = {'main': [all_targets]}
    print(f'Router connections: {len(all_targets)} nodes all on output 0')

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
if not r4.ok:
    print('Error:', r4.json().get('message', r4.text)[:500])

s.close()
