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

# Fix 1: All Telegram nodes - fix chatId to handle callback_query
for node in nodes:
    if node.get('type') != 'n8n-nodes-base.telegram':
        continue
    params = node.get('parameters', {})
    chat_id = params.get('chatId', '')

    # Replace $json.message.chat.id with expression that handles both cases
    if '$json.message.chat.id' in chat_id and 'callback_query' not in chat_id:
        params['chatId'] = '={{ ($json.message || $json.callback_query.message).chat.id }}'
        print(f'chatId: {node["name"]}')

# Fix 2: Code nodes - replace JSON string keyboards with objects
# Fix 3: Code nodes - use native fetch instead of polyfill
# (But polyfill works, so let's not break things)

# Fix 4: Start Welcome - change kb to object
for node in nodes:
    if node.get('type') != 'n8n-nodes-base.code':
        continue
    code = node.get('parameters', {}).get('jsCode', '')
    name = node.get('name', '')

    # Find JSON string keyboards like: const kb = '{"inline_keyboard":...
    # Replace with object keyboards
    if "const kb = '{\"inline_keyboard\"" in code or "const kb = '{\"inline_keyboard\"" in code:
        # Try to find and replace kb JSON strings
        import re

        # Match: const kb = '{"inline_keyboard":[[{...}]]}';
        kb_match = re.search(r"const kb = '(\{[^']+\})';", code)
        if kb_match:
            kb_json_str = kb_match.group(1)
            try:
                kb_obj = json.loads(kb_json_str)
                # Replace the string with object notation
                old_kb = kb_match.group(0)
                new_kb = "const kb = " + json.dumps(kb_obj, ensure_ascii=False) + ";"
                code = code.replace(old_kb, new_kb)
                node['parameters']['jsCode'] = code
                print(f'kb object: {name}')
            except json.JSONDecodeError as e:
                print(f'  JSON parse error in {name}: {e}')

    # Also find: const kb = JSON.stringify({...})
    # These should become: const kb = {...};

# Upload
r2 = s.patch(f'{BASE}/rest/workflows/{V2_ID}', json={'nodes': nodes})
print(f'Update: {r2.status_code}')
if not r2.ok:
    print('Error:', r2.text[:500])
    sys.exit(1)

# Activate
r3 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf2 = r3.json().get('data', r3.json())

# Verify
for n in wf2.get('nodes', []):
    if n.get('name') == 'Send Start Welcome':
        chat_id = n.get('parameters', {}).get('chatId', '')
        print(f'chatId: {chat_id[:80]}')
    if n.get('name') == 'Start Welcome':
        code = n.get('parameters', {}).get('jsCode', '')
        if 'inline_keyboard' in code and "const kb =" in code:
            # Show the kb line
            for line in code.split('\n'):
                if 'const kb' in line:
                    print(f'kb: {line.strip()[:120]}')
                    break

v = wf2.get('versionId')
r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': v}, timeout=60)
print(f'Activate: {r4.status_code}')
if not r4.ok:
    print('Error:', r4.json().get('message', r4.text)[:500])

s.close()
