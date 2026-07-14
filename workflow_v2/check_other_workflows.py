"""Check if there are other active workflows (e.g., old V1)"""
import requests, sys, json
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)

r = s.get(f'{BASE}/rest/workflows')
data = r.json()

# Handle different response formats
if isinstance(data, list):
    workflows = data
elif isinstance(data, dict):
    workflows = data.get('data', data).get('data', data)
    if isinstance(workflows, list):
        pass
    else:
        workflows = data.get('data', data).get('results', [])
else:
    print(f'Unexpected type: {type(data)}')
    print(r.text[:500])
    sys.exit(1)

print(f'Found {len(workflows)} workflows:\n')
for wf in workflows:
    name = wf.get('name', 'unknown')
    wf_id = wf.get('id', 'unknown')
    active = wf.get('active', False)
    updated = wf.get('updatedAt', 'unknown')
    print(f'  [{wf_id}] {name}')
    print(f'    active={active}, updated={updated}')

    # If it's active and not our V2, deactivate it
    if active and wf_id != 'oV8dWIoAUHRkLaSb':
        print(f'    *** DEACTIVATING: {name} ***')
        deact = s.post(f'{BASE}/rest/workflows/{wf_id}/deactivate', timeout=30)
        print(f'    Deactivate: {deact.status_code}')

s.close()
