"""Fix Polling Cron rule format to match other Schedule nodes"""
import requests, sys, json
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)
V2_ID = 'oV8dWIoAUHRkLaSb'

r = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf = r.json().get('data', r.json())
nodes = wf.get('nodes', [])

# Fix Polling Cron: use correct interval array format
for node in nodes:
    if node.get('name') == 'Polling Cron':
        node['parameters']['rule'] = {
            'interval': [{'field': 'seconds', 'secondsInterval': 10}]
        }
        print('Fixed Polling Cron rule format: interval array')
        break

# Also delete the test clone we created
try:
    s.delete(f'{BASE}/rest/workflows/PcFg9vqMDq28EMjI', timeout=10)
    print('Deleted test clone')
except:
    pass

# Upload
r2 = s.patch(f'{BASE}/rest/workflows/{V2_ID}', json={'nodes': nodes})
print(f'Update: {r2.status_code}')
if not r2.ok:
    print('Error:', r2.text[:500])
    sys.exit(1)

# Activate
r3 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf2 = r3.json().get('data', r3.json())
v = wf2.get('versionId')

r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': v}, timeout=60)
print(f'Activate: {r4.status_code}')
if r4.ok:
    print('WORKFLOW ACTIVATED!')
else:
    print('Error:', r4.json().get('message', r4.text)[:500])

s.close()
