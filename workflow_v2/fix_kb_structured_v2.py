"""Fix Send Start Welcome: use proper replyMarkup + inlineKeyboard structure"""
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

# Fix Send Start Welcome: use proper top-level replyMarkup with inlineKeyboard
for node in nodes:
    if node.get('name') == 'Send Start Welcome':
        params = node.get('parameters', {})

        # Remove the old additionalFields.reply_markup
        af = params.get('additionalFields', {})
        af.pop('reply_markup', None)

        # Set proper top-level replyMarkup with structured inlineKeyboard
        params['replyMarkup'] = 'inlineKeyboard'
        params['inlineKeyboard'] = {
            'rows': [
                {
                    'row': {
                        'buttons': [
                            {
                                'text': 'Проверить подписку',
                                'additionalFields': {
                                    'callbackData': 'SUB_CONFIRMED'
                                }
                            }
                        ]
                    }
                }
            ]
        }

        print(f'Fixed Send Start Welcome: replyMarkup=inlineKeyboard')
        print(f'  Params: {json.dumps(params, ensure_ascii=False, indent=2)}')
        break

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
if not r4.ok:
    print('Error:', r4.json().get('message', r4.text)[:500])
    sys.exit(1)

print('WORKFLOW ACTIVATED!')

# Verify
for n in wf2.get('nodes', []):
    if n.get('name') == 'Send Start Welcome':
        p = n.get('parameters', {})
        print(f'VERIFY replyMarkup: {p.get("replyMarkup")}')
        ik = p.get('inlineKeyboard', {})
        rows = ik.get('rows', [])
        if rows:
            btn = rows[0].get('row', {}).get('buttons', [{}])[0]
            print(f'  Button: {btn.get("text")} -> {btn.get("additionalFields", {}).get("callbackData")}')

s.close()
