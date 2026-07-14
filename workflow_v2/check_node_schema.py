"""Check n8n API for node schema info"""
import requests, sys, json
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)

# Try different endpoints
for endpoint in [
    '/rest/node-types/n8n-nodes-base.telegram',
    '/rest/workflows/node-types/n8n-nodes-base.telegram',
    '/rest/nodes/n8n-nodes-base.telegram',
    '/rest/node-types',
]:
    r = s.get(f'{BASE}{endpoint}')
    ct = r.headers.get('content-type', '')
    print(f'{endpoint}: status={r.status_code}, content-type={ct[:60]}, len={len(r.text)}')
    if 'json' in ct:
        data = r.json()
        if isinstance(data, list):
            print(f'  list of {len(data)} items')
            # Find telegram
            for item in data:
                if 'telegram' in str(item.get('name', '')).lower():
                    print(f'  Found: {item.get("name")}')
                    break
        elif isinstance(data, dict):
            keys = list(data.keys())
            print(f'  keys: {keys[:10]}')
    else:
        print(f'  text: {r.text[:200]}')
    print()

s.close()
