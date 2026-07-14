"""Find the corrupted parameter causing activation failure"""
import requests, sys, json
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)
V2_ID = 'oV8dWIoAUHRkLaSb'

r = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf = r.json().get('data', r.json())
nodes = wf.get('nodes', [])
conns = wf.get('connections', {})

print(f'Total nodes: {len(nodes)}')

# Check for nodes with potentially invalid parameters
for node in nodes:
    name = node.get('name', '?')
    ntype = node.get('type', '?')
    params = node.get('parameters', {})

    # Check node types
    issues = []

    # Check for replyMarkup as top-level (might conflict with typeVersion=1)
    if 'replyMarkup' in params:
        issues.append(f'has top-level replyMarkup={params["replyMarkup"]}')

    # Check for inlineKeyboard struct
    if 'inlineKeyboard' in params:
        issues.append('has inlineKeyboard param')

    # Check for sendTelegram in code
    if ntype == 'n8n-nodes-base.code' and 'jsCode' in params:
        code = params['jsCode']
        if 'async function sendTelegram' in code:
            issues.append('has sendTelegram helper')

    # Check for empty additionalFields
    af = params.get('additionalFields', {})
    if af == {}:
        issues.append('has EMPTY additionalFields object')

    # Check for potentially problematic params
    for k, v in params.items():
        if v is None:
            issues.append(f'param "{k}" is None')
        elif v == '' and k not in ('text', 'url', 'jsCode', 'chatId'):
            issues.append(f'param "{k}" is empty string')

    if issues:
        print(f'\n[{name}] ({ntype}):')
        for issue in issues:
            print(f'  - {issue}')

# Also check connections
print(f'\nConnections: {len(conns)} entries')
empty_conns = [k for k, v in conns.items() if v.get('main', []) == []]
if empty_conns:
    print(f'Empty connections: {empty_conns}')

s.close()
