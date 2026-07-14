"""Debug: try to activate after reverting polling changes"""
import requests, sys, json
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)
V2_ID = 'oV8dWIoAUHRkLaSb'

r = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf = r.json().get('data', r.json())
nodes = wf.get('nodes', [])

# Check Polling Cron current params
for n in nodes:
    if n.get('name') == 'Polling Cron':
        print('Polling Cron params:')
        print(json.dumps(n.get('parameters', {}), ensure_ascii=False, indent=2))
    if n.get('name') == 'Prepare URL':
        code = n.get('parameters', {}).get('jsCode', '')
        print(f'\nPrepare URL timeout line:')
        for line in code.split('\n'):
            if 'timeout' in line:
                print(f'  {line.strip()}')

# Try reverting Polling Cron to original interval
for n in nodes:
    if n.get('name') == 'Polling Cron':
        n['parameters']['rule'] = {'secondsInterval': 5, 'field': 'seconds'}
        print('\nReverted Polling Cron to 5s interval')
        break

# Upload
r2 = s.patch(f'{BASE}/rest/workflows/{V2_ID}', json={'nodes': nodes})
print(f'Update: {r2.status_code}')

# Try activate
r3 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf2 = r3.json().get('data', r3.json())
v = wf2.get('versionId')
r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': v}, timeout=60)
print(f'Activate: {r4.status_code}')
if not r4.ok:
    print('Error:', r4.json().get('message', r4.text)[:500])

s.close()
