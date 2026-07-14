"""Fix keyboard: send Telegram messages directly from Code nodes via fetch/proxy.
This bypasses the n8n Telegram node's reply_markup handling entirely."""
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
conns = wf.get('connections', {})

BOT_TOKEN = '8589709724:AAF8R-tki276jyAw69b1EhAEm2hp-5E2j_I'

# Helper to send message directly to Telegram via HTTP proxy
SEND_TG_HELPER = '''
// Helper: send Telegram message directly via proxy (bypasses n8n Telegram node)
async function sendTelegram(chatId, text, replyMarkup) {
  const url = 'https://api.telegram.org/bot' + BOT_TOKEN + '/sendMessage';
  const body = { chat_id: chatId, text: text };
  if (replyMarkup) { body.reply_markup = replyMarkup; }
  return await _n8nThis.helpers.httpRequest({
    url: url,
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body
  });
}
'''.replace('BOT_TOKEN', f"'{BOT_TOKEN}'")

# List of Code node → what message they send
# Each entry: (code_node_name, has_keyboard, connects_to_telegram_node)
fixes = []

for node in nodes:
    if node.get('type') != 'n8n-nodes-base.code':
        continue
    name = node.get('name', '')
    code = node.get('parameters', {}).get('jsCode', '')

    # Only fix Code nodes that output replyKeyboard
    if "'replyKeyboard'" not in code and '"replyKeyboard"' not in code and 'replyKeyboard:' not in code:
        continue

    # Check if this Code node has the _n8nThis polyfill
    if '_n8nThis' not in code and 'const _n8nThis = this;' not in code:
        continue

    has_polyfill = 'const _n8nThis = this;' in code

    # Find the matching Telegram node
    # Code node connections show what it connects to
    code_conns = conns.get(name, {}).get('main', [])
    tg_node_name = None
    for output_branch in code_conns:
        for tgt in output_branch:
            tgt_name = tgt.get('node', '')
            # Check if target is a Telegram node
            for n2 in nodes:
                if n2.get('name') == tgt_name and n2.get('type') == 'n8n-nodes-base.telegram':
                    tg_node_name = tgt_name
                    break
            if tg_node_name:
                break
        if tg_node_name:
            break

    if not tg_node_name:
        print(f'SKIP {name}: no Telegram node connection found')
        continue

    # Get the Telegram node params
    tg_params = {}
    for n2 in nodes:
        if n2.get('name') == tg_node_name:
            tg_params = n2.get('parameters', {})
            break

    print(f'Fixing: {name} -> {tg_node_name}')

    # Add sendTelegram helper if not already present
    if 'async function sendTelegram' not in code:
        # Insert after the _n8nThis line
        if has_polyfill:
            code = code.replace(
                'const _n8nThis = this;',
                'const _n8nThis = this;\n' + SEND_TG_HELPER
            )
        else:
            # Add both
            code = 'const _n8nThis = this;\n' + SEND_TG_HELPER + '\n' + code

    # Find where kb is defined and the return statement
    import re

    # Find: const kb = {...};
    # After the kb definition, add a sendTelegram call
    # And replace the return to include the kb in the Telegram send

    kb_match = re.search(r"const kb = (\{[^;]+\});", code)
    if kb_match:
        kb_obj_str = kb_match.group(1)
        try:
            kb_obj = json.loads(kb_obj_str)
        except:
            print(f'  WARNING: could not parse kb JSON in {name}')
            continue

        # Check if sendTelegram call already exists
        if 'sendTelegram(chatId' in code:
            print(f'  Already has sendTelegram')
            continue

        # Extract chatId from Telegram node
        tg_chat_id = tg_params.get('chatId', '')
        tg_text = tg_params.get('text', '')

        # Determine the chatId expression to use in the Code node
        # The Code node receives the input from App Config (which has the Telegram message data)
        chat_id_expr = "($input.first().json.message || $input.first().json.callback_query.message).chat.id"

        # Insert sendTelegram call BEFORE the return statement
        send_call = f'''
// Send message with keyboard directly via Telegram API
const chatId = {chat_id_expr};
await sendTelegram(chatId, text, kb).catch(e => console.log('sendTelegram error:', e));
'''
        # Insert after kb definition
        code = code.replace(
            kb_match.group(0),
            kb_match.group(0) + send_call
        )
        print(f'  Added sendTelegram call')

    node['parameters']['jsCode'] = code
    fixes.append(name)

print(f'\nFixed {len(fixes)} Code nodes:')
for f in fixes:
    print(f'  - {f}')

# Remove the connections from Code nodes to Telegram nodes (since we send directly)
# Keep the Telegram nodes in the workflow (they might still receive data but won't duplicate)
# Actually, let's remove connections so Telegram nodes don't run
for node in nodes:
    if node.get('type') != 'n8n-nodes-base.code':
        continue
    name = node.get('name', '')
    if name not in fixes:
        continue

    # Find Telegram connection
    node_conns = conns.get(name, {}).get('main', [])
    new_conns = []
    for output_branch in node_conns:
        new_branch = []
        for tgt in output_branch:
            tgt_name = tgt.get('node', '')
            # Check if it's a Telegram node
            is_telegram = False
            for n2 in nodes:
                if n2.get('name') == tgt_name and n2.get('type') == 'n8n-nodes-base.telegram':
                    is_telegram = True
                    break
            if not is_telegram:
                new_branch.append(tgt)
            else:
                print(f'  Removed connection: {name} -> {tgt_name}')
        if new_branch:
            new_conns.append(new_branch)

    if new_conns:
        conns[name] = {'main': new_conns}
    else:
        conns.pop(name, None)

# Upload
r2 = s.patch(f'{BASE}/rest/workflows/{V2_ID}', json={'nodes': nodes, 'connections': conns})
print(f'Update: {r2.status_code}')
if not r2.ok:
    print('Error:', r2.text[:500])
    sys.exit(1)

# Verify
r3 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf2 = r3.json().get('data', r3.json())
for n in wf2.get('nodes', []):
    if n.get('name') == 'Start Welcome':
        code = n.get('parameters', {}).get('jsCode', '')
        if 'sendTelegram' in code:
            print('VERIFIED: Start Welcome has sendTelegram')
            # Show the relevant part
            for line in code.split('\n'):
                if 'sendTelegram' in line:
                    print(f'  {line.strip()[:150]}')
        else:
            print('WARNING: sendTelegram NOT in Start Welcome!')
        break

# Activate
v = wf2.get('versionId')
r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': v}, timeout=60)
print(f'Activate: {r4.status_code}')
if not r4.ok:
    print('Error:', r4.json().get('message', r4.text)[:500])

s.close()
