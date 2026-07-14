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

# First, deactivate
s.post(f'{BASE}/rest/workflows/{V2_ID}/deactivate', timeout=30)

# Test 1: Can we use Switch V3?
for node in nodes:
    if node.get('name') == 'Router':
        # Try V3 with simple expression
        node['typeVersion'] = 3
        node['parameters'] = {
            "mode": "expression",
            "numberOutputs": 26,
            "output": "(() => { const r = $json._route; return (typeof r === 'number' && r >= 0 && r < 26) ? r : 0; })()"
        }
        print('Trying Switch V3...')

r2 = s.patch(f'{BASE}/rest/workflows/{V2_ID}', json={'nodes': nodes})
print(f'Update (V3): {r2.status_code}')
if r2.ok:
    # Try activate
    r3 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
    wf2 = r3.json().get('data', r3.json())
    version_id = wf2.get('versionId')
    r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': version_id}, timeout=60)
    print(f'Activate (V3): {r4.status_code}')
    if r4.ok:
        print('Switch V3 WORKS!')
    else:
        err = r4.json().get('message', r4.text)[:300]
        print(f'Activation error: {err}')
        # Fall back to multiple Switch approach
else:
    print(f'Update error: {r2.text[:300]}')
    print('V3 not supported, will split into multiple Switch nodes')

s.close()
