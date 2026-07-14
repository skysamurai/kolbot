import requests, json, sys
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'})
V2_ID = 'oV8dWIoAUHRkLaSb'

# Deactivate first
r = s.post(f'{BASE}/rest/workflows/{V2_ID}/deactivate')
print(f'Deactivate: {r.status_code}')

# Get workflow
r = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf = r.json().get('data', r.json())
nodes = wf.get('nodes', [])
conns = wf.get('connections', {})

# 1. Remove ALL Polling nodes (they're broken/non-standard approach)
nodes = [n for n in nodes if not n.get('name', '').startswith('Poll')]
print(f'After removing Poll nodes: {len(nodes)}')

# 2. Remove duplicate Telegram Trigger if any
telegram_triggers = [n for n in nodes if n.get('type') == 'n8n-nodes-base.telegramTrigger']
print(f'Telegram triggers: {len(telegram_triggers)}')

# 3. Instead of custom polling, let's try the Telegram Trigger with webhook approach
# But first, delete the Telegram webhook so n8n doesn't try to set one
# Then configure Telegram Trigger with proxy-compatible settings

# Re-add Telegram Trigger if missing
has_tg_trigger = any(n.get('type') == 'n8n-nodes-base.telegramTrigger' for n in nodes)
if not has_tg_trigger:
    tg_trigger = {
        'id': 'tg-trigger-v2',
        'name': 'Telegram Trigger',
        'type': 'n8n-nodes-base.telegramTrigger',
        'typeVersion': 1,
        'position': [0, 300],
        'parameters': {
            'updates': ['message', 'callback_query'],
            'additionalFields': {'useLongPolling': True}
        },
        'credentials': {'telegramApi': {'id': 'b1x5cXjr8PBaOxPy', 'name': 'CH-SPA Bot Token'}}
    }
    nodes.append(tg_trigger)
    print('Re-added Telegram Trigger with long polling')

# 4. Fix connections: remove Poll connections, restore Telegram Trigger connection
conns.pop('Polling Cron', None)
conns.pop('Poll Telegram', None)
conns['Telegram Trigger'] = {'main': [[{'node': 'App Config', 'type': 'main', 'index': 0}]]}

# 5. Make sure App Config has TELEGRAM_BOT_TOKEN
for node in nodes:
    if node.get('name') == 'App Config':
        code = node['parameters']['jsCode']
        if "TELEGRAM_BOT_TOKEN" not in code:
            # Add bot token config
            old = "const subscriptionChannelId = String('@ch_spa').trim();"
            new = "const botToken = String('8589709724:AAF8R-tki276jyAw69b1EhAEm2hp-5E2j_I').trim();\nconst subscriptionChannelId = String('@ch_spa').trim();"
            code = code.replace(old, new)
            if 'TELEGRAM_BOT_TOKEN:' not in code:
                code = code.replace(
                    'SUPABASE_CONFIGURED: !!(',
                    'TELEGRAM_BOT_TOKEN: botToken,\n  SUPABASE_CONFIGURED: !!('
                )
            node['parameters']['jsCode'] = code
            print('Added TELEGRAM_BOT_TOKEN to App Config')

# Upload
r2 = s.patch(f'{BASE}/rest/workflows/{V2_ID}', json={'nodes': nodes, 'connections': conns})
print(f'Update: {r2.status_code}')
if not r2.ok:
    print('Error:', r2.text[:500])
    sys.exit(1)

# List final nodes
r3 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf2 = r3.json().get('data', r3.json())
print(f'\nFinal node count: {len(wf2.get("nodes", []))}')
for n in wf2.get('nodes', []):
    name = n.get('name', '?')
    ntype = n.get('type', '').split('.')[-1]
    if 'Cron' in name or 'Trigger' in name or 'Webhook' in name or 'Poll' in name:
        print(f'  {name} ({ntype})')

s.close()
