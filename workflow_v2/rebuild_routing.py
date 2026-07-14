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

# Strategy: Replace single 26-output Router with a chain of IF nodes
# Each IF node checks if _route equals a specific value
# True -> specific handler, False -> next IF in chain
# This avoids the Switch V1 $json bug because IF nodes use structured conditions

# The targets for each route (0-25)
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

# Get Router position to place new nodes nearby
router_pos = [660, 300]
for node in nodes:
    if node.get('name') == 'Router':
        router_pos = node.get('position', router_pos)

# Remove old Router
nodes = [n for n in nodes if n.get('name') != 'Router']
conns.pop('Router', None)

# Create chain of IF nodes
if_nodes = []
for i in range(25):  # 25 IF nodes (0-24), route 25 is automatic fallthrough
    node_name = f'Route {i}'
    if_node = {
        'id': f'route-if-{i}',
        'name': node_name,
        'type': 'n8n-nodes-base.if',
        'typeVersion': 2,
        'position': [router_pos[0] + i * 160, router_pos[1]],
        'parameters': {
            'conditions': {
                'options': {
                    'caseSensitive': True,
                    'leftValue': '',
                    'operator': 'numberEquals',
                    'typeValidation': 'strict',
                    'version': 2
                },
                'conditions': [
                    {
                        'id': f'route-cond-{i}',
                        'leftValue': '={{ $json._route }}',
                        'rightValue': i,
                        'operator': 'numberEquals'
                    }
                ],
                'combinator': 'and'
            }
        }
    }
    nodes.append(if_node)
    if_nodes.append(node_name)

# Connections: IF chain
# Upsert User -> Route 0
# Route 0 true -> Start Welcome
# Route 0 false -> Route 1
# Route 1 true -> Check Subscription
# Route 1 false -> Route 2
# ...
# Route 24 true -> Upsell No
# Route 24 false -> Phone As Text (route 25)

# Upsert User -> Route 0
conns['Upsert User'] = {
    'main': [[{'node': 'Route 0', 'type': 'main', 'index': 0}]]
}

for i in range(25):
    node_name = if_nodes[i]
    target = route_targets[i]

    if i < 24:
        next_if = if_nodes[i + 1]
        conns[node_name] = {
            'main': [
                [{'node': target, 'type': 'main', 'index': 0}],    # true -> handler
                [{'node': next_if, 'type': 'main', 'index': 0}]    # false -> next IF
            ]
        }
    else:
        # Last IF (route 24): false -> route 25 (Phone As Text)
        conns[node_name] = {
            'main': [
                [{'node': target, 'type': 'main', 'index': 0}],              # true -> route 24
                [{'node': route_targets[25], 'type': 'main', 'index': 0}]    # false -> route 25
            ]
        }

print(f'Created {len(if_nodes)} IF nodes in chain')
print(f'Total nodes: {len(nodes)}')

# Upload
r2 = s.patch(f'{BASE}/rest/workflows/{V2_ID}', json={'nodes': nodes, 'connections': conns})
print(f'Update: {r2.status_code}')
if not r2.ok:
    print('Error:', r2.text[:500])
    sys.exit(1)

# Verify $json in IF conditions
r3 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf2 = r3.json().get('data', r3.json())
for n in wf2.get('nodes', []):
    if n.get('name') == 'Route 0':
        conds = n.get('parameters', {}).get('conditions', {})
        first_cond = conds.get('conditions', [{}])[0]
        lv = first_cond.get('leftValue', '')
        if '$json' in lv:
            print('$json PRESERVED in IF condition!')
        else:
            print(f'WARNING: $json missing: {lv}')
        break

# Activate
v = wf2.get('versionId')
r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': v}, timeout=60)
print(f'Activate: {r4.status_code}')
if not r4.ok:
    print('Error:', r4.json().get('message', r4.text)[:500])

s.close()
