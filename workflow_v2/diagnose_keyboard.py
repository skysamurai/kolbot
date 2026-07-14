"""Diagnose keyboard issue: check exact Telegram node params and Code node output"""
import requests, sys, json
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)
V2_ID = 'oV8dWIoAUHRkLaSb'

r = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf = r.json().get('data', r.json())
nodes = wf.get('nodes', [])

print('=' * 60)
print('SEND START WELCOME (Telegram node)')
print('=' * 60)
for n in nodes:
    if n.get('name') == 'Send Start Welcome':
        print(f'type: {n.get("type")}')
        print(f'typeVersion: {n.get("typeVersion")}')
        params = n.get('parameters', {})
        print(f'parameters keys: {list(params.keys())}')
        for k, v in params.items():
            if k == 'additionalFields':
                print(f'additionalFields: {json.dumps(v, ensure_ascii=False, indent=2)}')
            else:
                val_str = str(v)
                if len(val_str) > 200:
                    val_str = val_str[:200] + '...'
                print(f'  {k}: {val_str}')

print()
print('=' * 60)
print('START WELCOME (Code node)')
print('=' * 60)
for n in nodes:
    if n.get('name') == 'Start Welcome':
        code = n.get('parameters', {}).get('jsCode', '')
        # Find the kb line
        for line in code.split('\n'):
            stripped = line.strip()
            if 'kb' in stripped.lower() or 'replyKeyboard' in stripped.lower() or 'inline_keyboard' in stripped.lower():
                print(f'  {stripped[:150]}')
        # Also check the return statement
        for line in code.split('\n'):
            if 'return' in line:
                print(f'  RETURN: {line.strip()[:200]}')
                break

print()
print('=' * 60)
print('CHECKING ALL TELEGRAM NODES WITH reply_markup')
print('=' * 60)
for n in nodes:
    if n.get('type') != 'n8n-nodes-base.telegram':
        continue
    params = n.get('parameters', {})
    af = params.get('additionalFields', {})
    if af and 'reply_markup' in str(af):
        rm = af.get('reply_markup', '')
        print(f'{n["name"]}: reply_markup = {str(rm)[:200]}')

print()
print('=' * 60)
print('CHECK EXECUTION HISTORY FOR ERRORS')
print('=' * 60)
r2 = s.get(f'{BASE}/rest/executions?workflowId={V2_ID}&limit=3')
try:
    execs = r2.json()
    for ex in execs.get('data', execs.get('results', []))[:3]:
        print(f'Execution {ex.get("id")}: status={ex.get("status")}, mode={ex.get("mode")}')
        if ex.get('status') == 'error':
            print(f'  Error: {str(ex.get("data", {}).get("resultData", {}).get("error", {}))[:300]}')
except:
    print(f'Raw: {r2.text[:500]}')

s.close()
