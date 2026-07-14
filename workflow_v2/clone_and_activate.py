"""Clone the workflow and try to activate the clone"""
import requests, sys, json
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)
V2_ID = 'oV8dWIoAUHRkLaSb'

# Get the full workflow
r = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf_data = r.json().get('data', r.json())

# Create a new workflow with same content
new_wf = {
    'name': 'CH-SPA V2 - Test',
    'nodes': wf_data.get('nodes', []),
    'connections': wf_data.get('connections', {}),
    'settings': wf_data.get('settings', {}),
    'staticData': wf_data.get('staticData', None),
}

r2 = s.post(f'{BASE}/rest/workflows', json=new_wf)
print(f'Create: {r2.status_code}')
if r2.ok:
    new_data = r2.json().get('data', r2.json())
    new_id = new_data.get('id')
    print(f'New workflow ID: {new_id}')

    # Try to activate
    v = new_data.get('versionId')
    r3 = s.post(f'{BASE}/rest/workflows/{new_id}/activate', json={'versionId': v}, timeout=60)
    print(f'Activate: {r3.status_code}')
    if not r3.ok:
        print('Error:', r3.json().get('message', r3.text)[:500])
    else:
        print('SUCCESS!')

    # Deactivate old one first, then delete the test
    # Keep the new one if it works
else:
    print('Error:', r2.text[:500])

s.close()
