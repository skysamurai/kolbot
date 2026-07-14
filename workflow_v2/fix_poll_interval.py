"""Fix polling: interval=10s, timeout=2s to prevent 409 overlap"""
import requests, sys, json
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)
V2_ID = 'oV8dWIoAUHRkLaSb'

s.post(f'{BASE}/rest/workflows/{V2_ID}/deactivate', timeout=30)

r = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf = r.json().get('data', r.json())
nodes = wf.get('nodes', [])

# Fix 1: Increase cron interval to 10 seconds
for node in nodes:
    if node.get('name') == 'Polling Cron':
        params = node.get('parameters', {})
        params['rule'] = {'secondsInterval': 10, 'field': 'seconds'}
        print('Polling interval: 10 seconds')
        break

# Fix 2: Keep getUpdates timeout at 2 seconds (must be < interval)
for node in nodes:
    if node.get('name') == 'Prepare URL':
        code = node.get('parameters', {}).get('jsCode', '')
        if 'timeout=10' in code:
            code = code.replace('timeout=10', 'timeout=2')
        elif 'timeout=2' not in code:
            # shouldn't happen
            pass
        node['parameters']['jsCode'] = code
        print('getUpdates timeout: 2 seconds')
        break

# Upload
r2 = s.patch(f'{BASE}/rest/workflows/{V2_ID}', json={'nodes': nodes})
print(f'Update: {r2.status_code}')
if not r2.ok:
    print('Error:', r2.text[:500])
    sys.exit(1)

# Activate
v_resp = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf2 = v_resp.json().get('data', v_resp.json())
v = wf2.get('versionId')
r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': v}, timeout=60)
print(f'Activate: {r4.status_code}')
if not r4.ok:
    print('Error:', r4.json().get('message', r4.text)[:500])

s.close()
