"""Fix: callbackData -> callback_data in inline keyboard"""
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

fixed = 0
for node in nodes:
    if node.get('name') == 'Send Start Welcome':
        params = node.get('parameters', {})
        ik = params.get('inlineKeyboard', {})
        rows = ik.get('rows', [])

        for row_wrapper in rows:
            buttons = row_wrapper.get('row', {}).get('buttons', [])
            for btn in buttons:
                af = btn.get('additionalFields', {})
                if 'callbackData' in af:
                    af['callback_data'] = af.pop('callbackData')
                    fixed += 1
                    print(f'Fixed: callbackData -> callback_data')

        # Also fix empty additionalFields
        if params.get('additionalFields') == {}:
            del params['additionalFields']
            print('Removed empty additionalFields')

        break

# Upload
r2 = s.patch(f'{BASE}/rest/workflows/{V2_ID}', json={'nodes': nodes})
print(f'Update: {r2.status_code}')

# Activate
r3 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf2 = r3.json().get('data', r3.json())
v = wf2.get('versionId')
r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': v}, timeout=60)
print(f'Activate: {r4.status_code}')
if not r4.ok:
    print('Error:', r4.json().get('message', r4.text)[:500])
else:
    print('DONE!')

# Verify
r5 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf3 = r5.json().get('data', r5.json())
for n in wf3.get('nodes', []):
    if n.get('name') == 'Send Start Welcome':
        p = n.get('parameters', {})
        ik = p.get('inlineKeyboard', {})
        rows = ik.get('rows', [])
        if rows:
            btn = rows[0].get('row', {}).get('buttons', [{}])[0]
            af = btn.get('additionalFields', {})
            print(f'VERIFY: {json.dumps(btn, ensure_ascii=False)}')

s.close()
