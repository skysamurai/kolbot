"""Add diagnostic console.log to Start Welcome to see what's happening"""
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

# Add logging wrapper to Start Welcome
for node in nodes:
    if node.get('name') == 'Start Welcome':
        code = node.get('parameters', {}).get('jsCode', '')

        # Add try/catch around the main logic with console.log
        # Find the return statement and wrap everything after the gate in try/catch
        old_return = 'return [{ json:'
        if old_return in code:
            # Add logging before return
            logged_code = code.replace(
                old_return,
                'console.log("Start Welcome: sending reply. replyText length=" + text.length + " chatId=" + ((input.message || input.callback_query.message).chat.id));\n' + old_return
            )
            node['parameters']['jsCode'] = logged_code
            print('Added diagnostic logging to Start Welcome')
        break

# Also log in Send Start Welcome - we can't add to Telegram node, but let's verify its params
for node in nodes:
    if node.get('name') == 'Send Start Welcome':
        params = node.get('parameters', {})
        print(f'Send Start Welcome params:')
        print(f'  text: {params.get("text", "")[:80]}')
        print(f'  chatId: {params.get("chatId", "")[:80]}')
        af = params.get('additionalFields', {})
        print(f'  reply_markup: {str(af.get("reply_markup", ""))[:120]}')
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

s.close()
