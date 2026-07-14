"""Full diagnostic: show Start Welcome Code node and its Telegram node"""
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

# Show Send Start Welcome Telegram node FULL params
print('=' * 60)
print('SEND START WELCOME - FULL PARAMS')
print('=' * 60)
for n in nodes:
    if n.get('name') == 'Send Start Welcome':
        print(f'type: {n.get("type")}')
        print(f'typeVersion: {n.get("typeVersion")}')
        print(f'id: {n.get("id")}')
        print(f'position: {n.get("position")}')
        print(f'ALL parameters:')
        print(json.dumps(n.get('parameters', {}), ensure_ascii=False, indent=2))
        break

# Show Start Welcome Code node FULL code
print()
print('=' * 60)
print('START WELCOME - FULL CODE')
print('=' * 60)
for n in nodes:
    if n.get('name') == 'Start Welcome':
        print(f'id: {n.get("id")}')
        print(f'position: {n.get("position")}')
        code = n.get('parameters', {}).get('jsCode', '')
        print(code)
        break

# Show connections around Send Start Welcome
print()
print('=' * 60)
print('CONNECTIONS INVOLVING SEND START WELCOME')
print('=' * 60)
for src, targets in conns.items():
    for output in targets.get('main', []):
        for tgt in output:
            if tgt.get('node') in ('Send Start Welcome', 'Start Welcome'):
                print(f'{src} -> {tgt["node"]}')

# Also show the Supabase/HTTP Request node that might be related
print()
print('=' * 60)
print('OTHER TELEGRAM NODES - CHECK REPLY_MARKUP FORMAT')
print('=' * 60)
for n in nodes:
    if n.get('type') != 'n8n-nodes-base.telegram':
        continue
    params = n.get('parameters', {})
    af = params.get('additionalFields', {})
    rm = af.get('reply_markup', '')
    if rm and rm != '={{ $json.replyKeyboard }}':
        print(f'{n["name"]}: reply_markup = {str(rm)[:150]}')

s.close()
