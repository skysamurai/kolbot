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

# Change the first Route 0 to use 'exists' operator
for node in nodes:
    if node.get('name') == 'Route 0':
        node['parameters']['conditions'] = {
            'options': {
                'caseSensitive': True,
                'leftValue': '',
                'operator': 'exists',
                'typeValidation': 'strict',
                'version': 2
            },
            'conditions': [
                {
                    'id': 'route-cond-0',
                    'leftValue': '={{ $json._route }}',
                    'operator': 'exists'
                }
            ],
            'combinator': 'and'
        }
        print('Route 0: using exists operator')

# Upload
r2 = s.patch(f'{BASE}/rest/workflows/{V2_ID}', json={'nodes': nodes})
print(f'Update: {r2.status_code}')

r3 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf2 = r3.json().get('data', r3.json())

# Verify
for n in wf2.get('nodes', []):
    if n.get('name') == 'Route 0':
        conds = n.get('parameters', {}).get('conditions', {})
        op = conds.get('conditions', [{}])[0].get('operator', '')
        lv = conds.get('conditions', [{}])[0].get('leftValue', '')
        print(f'Operator: {op}, LeftValue: {lv[:50]}')
        break

v = wf2.get('versionId')
r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': v}, timeout=60)
print(f'Activate: {r4.status_code}')
if not r4.ok:
    print('Error:', r4.json().get('message', r4.text)[:300])

s.close()
