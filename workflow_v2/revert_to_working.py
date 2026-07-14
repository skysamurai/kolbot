"""Revert to known-working state: text arrives, keyboard is hardcoded JSON string"""
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

# Fix Send Start Welcome: revert to simple additionalFields.reply_markup (hardcoded JSON string)
for node in nodes:
    if node.get('name') == 'Send Start Welcome':
        params = node.get('parameters', {})

        # Remove the structured keyboard (V2 format)
        params.pop('replyMarkup', None)
        params.pop('inlineKeyboard', None)

        # Restore the original format
        params['additionalFields'] = {
            'reply_markup': '{"inline_keyboard":[[{"text":"Проверить подписку","callback_data":"SUB_CONFIRMED"}]]}'
        }
        print('Reverted Send Start Welcome to simple format')
        break

# Also revert Start Welcome Code node to original (no JSON.stringify on kb)
# Output kb as object (to match what the original workflow had)
for node in nodes:
    if node.get('name') == 'Start Welcome':
        code = node.get('parameters', {}).get('jsCode', '')
        # Check if we need to fix the kb output
        if 'JSON.stringify' in code:
            code = code.replace(
                'const kb = JSON.stringify({"inline_keyboard": [[{"text": "Проверить подписку", "callback_data": "SUB_CONFIRMED"}]]});',
                'const kb = {"inline_keyboard": [[{"text": "Проверить подписку", "callback_data": "SUB_CONFIRMED"}]]};'
            )
            node['parameters']['jsCode'] = code
            print('Reverted Start Welcome: kb as object (not JSON.stringify)')
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
else:
    print('WORKFLOW ACTIVE - Test /start now')

s.close()
