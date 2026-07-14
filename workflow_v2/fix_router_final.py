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
conns = wf.get('connections', {})

# Fix Router with proper $json (preserved in .py file)
router_expr = """// Read _route from data (set by App Config)
// Use $json._route for routing, fallback to 0
$json._route || 0"""

for node in nodes:
    if node.get('name') == 'Router':
        node['type'] = 'n8n-nodes-base.switch'
        node['typeVersion'] = 1
        node['parameters'] = {
            'mode': 'expression',
            'numberOutputs': 26,
            'output': router_expr
        }
        print(f'Router expression: {router_expr}')

# Restore all 26 Router connections
route_targets = [
    'Start Welcome', 'Check Subscription', 'Sub Confirmed', 'Save Contact',
    'Save Package Standard', 'Save Package Premium', 'Save Package VIP',
    'Save Photo V2', 'Admin Approve Purchase', 'Admin Reject Purchase',
    'Start Review', 'Save Marketplace', 'Save Rev Screenshot',
    'Save Rev Prod Photo', 'Admin Approve Review', 'Admin Reject Review',
    'Build Status', 'Build Back', 'Build Continue', 'Reset State',
    'Help Message', 'Admin Export', 'Admin Commands',
    'Upsell Yes', 'Upsell No', 'Phone As Text'
]

router_conns = []
for target in route_targets:
    router_conns.append([[{'node': target, 'type': 'main', 'index': 0}]])
conns['Router'] = {'main': router_conns}

r2 = s.patch(f'{BASE}/rest/workflows/{V2_ID}', json={'nodes': nodes, 'connections': conns})
print(f'Update: {r2.status_code}')
if not r2.ok:
    print('Error:', r2.text[:500])
    sys.exit(1)

r3 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf2 = r3.json().get('data', r3.json())

# Verify $json is preserved
for n in wf2.get('nodes', []):
    if n.get('name') == 'Router':
        expr = n.get('parameters', {}).get('output', '')
        print(f'Verified expression: {expr[:80]}')
        if '$json' in expr:
            print('$json PRESERVED!')
        else:
            print('WARNING: $json STILL MISSING!')
        break

v = wf2.get('versionId')
r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': v}, timeout=60)
print(f'Activate: {r4.status_code}')
if not r4.ok:
    print('Error:', r4.json().get('message', r4.text)[:500])
else:
    print('Workflow activated!')

s.close()
