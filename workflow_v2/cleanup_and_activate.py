"""Clean up empty additionalFields and revert broken sendTelegram additions, then activate"""
import requests, sys, json, re
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)
V2_ID = 'oV8dWIoAUHRkLaSb'

r = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf = r.json().get('data', r.json())
nodes = wf.get('nodes', [])
conns = wf.get('connections', {})

cleaned = 0
reverted = 0

for node in nodes:
    params = node.get('parameters', {})
    name = node.get('name', '')

    # Remove empty additionalFields
    af = params.get('additionalFields')
    if af is not None and (af == {} or af == [] or af == ''):
        del params['additionalFields']
        cleaned += 1

    # Revert sendTelegram additions in Auto-Approve Worker and Followup Worker
    if name in ('Auto-Approve Worker', 'Followup Worker'):
        code = params.get('jsCode', '')
        if 'async function sendTelegram' in code:
            # Remove the sendTelegram helper function
            code = re.sub(
                r'\n// Helper: send Telegram message directly via proxy.*?\n\}\n',
                '\n',
                code,
                flags=re.DOTALL
            )
            # Remove sendTelegram calls
            code = re.sub(
                r'\n// Send message with keyboard directly via Telegram API.*?\nawait sendTelegram\(chatId,.*?;\n',
                '\n',
                code,
                flags=re.DOTALL
            )
            # Remove the chatId extraction for direct send
            code = re.sub(
                r'\nconst chatId = \(.*?\.chat\.id;\n',
                '\n',
                code
            )
            params['jsCode'] = code
            reverted += 1
            print(f'Reverted sendTelegram from: {name}')

    # Restore connections from reverted nodes to their Telegram nodes
    if name == 'Auto-Approve Worker':
        conns['Auto-Approve Worker'] = {
            'main': [[{'node': 'Send Approve Messages', 'type': 'main', 'index': 0}]]
        }
        print('Restored: Auto-Approve Worker -> Send Approve Messages')

    if name == 'Followup Worker':
        conns['Followup Worker'] = {
            'main': [[{'node': 'Send Followup Messages', 'type': 'main', 'index': 0}]]
        }
        print('Restored: Followup Worker -> Send Followup Messages')

print(f'Cleaned {cleaned} empty additionalFields')
print(f'Reverted {reverted} Code nodes')

# Upload
r2 = s.patch(f'{BASE}/rest/workflows/{V2_ID}', json={'nodes': nodes, 'connections': conns})
print(f'Update: {r2.status_code}')
if not r2.ok:
    print('Error:', r2.text[:500])
    sys.exit(1)

# Activate
r3 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf2 = r3.json().get('data', r3.json())
v = wf2.get('versionId')
print(f'Version: {v}')

r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': v}, timeout=60)
print(f'Activate: {r4.status_code}')
if not r4.ok:
    print('Error:', r4.json().get('message', r4.text)[:500])
    sys.exit(1)

print('Workflow activated!')

s.close()
