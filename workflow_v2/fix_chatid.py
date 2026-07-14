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

# Fix chatId in all Telegram nodes to handle both message and callback_query
# Old: ={{ $json.message.chat.id }}
# New: ={{ ($json.message || $json.callback_query.message).chat.id }}
fixed = 0
for node in nodes:
    if node.get('type') != 'n8n-nodes-base.telegram':
        continue

    params = node.get('parameters', {})
    chat_id = params.get('chatId', '')

    if '$json.message.chat.id' in chat_id:
        # Fix to handle callback_query too
        new_chat_id = chat_id.replace(
            '$json.message.chat.id',
            '($json.message || $json.callback_query.message).chat.id'
        )
        params['chatId'] = new_chat_id
        fixed += 1
        print(f'Fixed chatId in: {node["name"]}')

print(f'\nFixed {fixed} Telegram nodes')

# Also check for other $json.message references in Telegram node text fields
# Some might need to handle callback_query context
for node in nodes:
    if node.get('type') != 'n8n-nodes-base.telegram':
        continue
    params = node.get('parameters', {})
    text = params.get('text', '')
    # These are replyText/replyKeyboard so they should come from Code nodes
    # which already handle the data correctly. No change needed.

# Upload
r2 = s.patch(f'{BASE}/rest/workflows/{V2_ID}', json={'nodes': nodes})
print(f'Update: {r2.status_code}')
if not r2.ok:
    print('Error:', r2.text[:500])
    sys.exit(1)

# Activate
r3 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf2 = r3.json().get('data', r3.json())

# Verify one
for n in wf2.get('nodes', []):
    if n.get('type') == 'n8n-nodes-base.telegram':
        chat_id = n.get('parameters', {}).get('chatId', '')
        if 'callback_query' in chat_id:
            print(f'VERIFIED: {n["name"]} handles callback_query')
            break

v = wf2.get('versionId')
r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': v}, timeout=60)
print(f'Activate: {r4.status_code}')
if not r4.ok:
    print('Error:', r4.json().get('message', r4.text)[:500])

s.close()
