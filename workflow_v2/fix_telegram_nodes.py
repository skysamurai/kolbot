import requests, json, sys
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'})
V2_ID = 'oV8dWIoAUHRkLaSb'

r = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf = r.json().get('data', r.json())
nodes = wf.get('nodes', [])
conns = wf.get('connections', {})

# Nodes that receive { chatId, text, ... } from code (not from trigger)
direct_chatid_nodes = {
    'Send Followup Messages', 'Send Approve Messages',
    'Send Daily Report', 'Send Payment Confirm'
}

fixed = 0
for node in nodes:
    if node['type'] != 'n8n-nodes-base.telegram':
        continue

    params = node.get('parameters', {})
    name = node.get('name', '')

    # Set required chatId
    if name in direct_chatid_nodes:
        params['chatId'] = '={{ $json.chatId }}'
    else:
        params['chatId'] = '={{ $json.message.chat.id }}'

    # Remove replyMarkup that my previous broken script added
    params.pop('replyMarkup', None)

    # Restore reply_markup in additionalFields for dynamic keyboards
    # Only set it when the expression produces a non-empty value
    af = params.get('additionalFields', {})
    af['reply_markup'] = '={{ $json.replyKeyboard }}'
    params['additionalFields'] = af

    fixed += 1

print(f'Fixed {fixed} Telegram nodes')

# Upload
r2 = s.patch(f'{BASE}/rest/workflows/{V2_ID}', json={'nodes': nodes, 'connections': conns})
print(f'Update: {r2.status_code}')
if r2.ok:
    # Verify
    r3 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
    wf2 = r3.json().get('data', r3.json())
    for n in wf2.get('nodes', []):
        if n.get('name') == 'Send Start Welcome':
            print('Sample node:')
            print(json.dumps(n, indent=2, ensure_ascii=False))
            break
else:
    print(f'Error: {r2.text[:500]}')

s.close()
