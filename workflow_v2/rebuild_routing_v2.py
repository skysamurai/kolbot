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

# Step 1: Remove all IF nodes (Route 0 through Route 24)
nodes = [n for n in nodes if not n.get('name', '').startswith('Route ')]
# Clean up connections
for key in list(conns.keys()):
    if key.startswith('Route '):
        del conns[key]

print(f'Nodes after cleanup: {len(nodes)}')

# Step 2: Add a Switch with hardcoded "0" (always routes to output 0)
# Connect all 26 targets to output 0
# Then each target's Code node will filter itself

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

# Find position for new Router
router_pos = [660, 300]

router = {
    'id': 'router-v2',
    'name': 'Router',
    'type': 'n8n-nodes-base.switch',
    'typeVersion': 1,
    'position': router_pos,
    'parameters': {
        'mode': 'expression',
        'numberOutputs': 26,
        'output': '0'
    }
}
nodes.append(router)

# Connect all targets to Router output 0
router_conns = [[{'node': t, 'type': 'main', 'index': 0}] for t in route_targets]
# Fill remaining 25 outputs with empty arrays
while len(router_conns) < 26:
    router_conns.append([])
conns['Router'] = {'main': router_conns}

# Connect Upsert User -> Router
conns['Upsert User'] = {'main': [[{'node': 'Router', 'type': 'main', 'index': 0}]]}

# Step 3: Add gate checks to each downstream Code node
# Each Code node gets a prefix that checks _route and returns [] if not matching
gates = {}
for i, target in enumerate(route_targets):
    for node in nodes:
        if node.get('name') == target and node.get('type') == 'n8n-nodes-base.code':
            code = node.get('parameters', {}).get('jsCode', '')
            # Add gate check at the beginning
            gate = f'// ROUTE GATE: only process if _route === {i}\nif ($input.first().json._route !== {i}) {{ return []; }}\n\n'
            if 'ROUTE GATE' not in code:
                # Insert after any initial comment block
                lines = code.split('\n')
                insert_at = 0
                for j, line in enumerate(lines):
                    if line.strip().startswith('//') or line.strip().startswith('/*'):
                        insert_at = j + 1
                    else:
                        break
                if insert_at == 0:
                    insert_at = 0
                lines.insert(insert_at, gate)
                node['parameters']['jsCode'] = '\n'.join(lines)
                gates[target] = i
                break

print(f'Added gates to {len(gates)} Code nodes: {list(gates.keys())}')

# For non-Code nodes that are direct Router targets, add a Code gate node before them
# Check which targets are NOT Code nodes
code_targets = set(gates.keys())
non_code_targets = []
for i, target in enumerate(route_targets):
    if target not in code_targets:
        non_code_targets.append((i, target))
        
print(f'Non-Code targets: {non_code_targets}')

# Add Code gate nodes before non-Code targets
# These simple Code nodes check _route and pass through or return []
for i, target in non_code_targets:
    gate_name = f'Gate {target}'
    gate_code = f'// Gate for route {i}: {target}\nconst item = $input.first();\nif (!item) {{ return []; }}\nif (item.json._route !== {i}) {{ return []; }}\nreturn [item];'
    
    gate_node = {
        'id': f'gate-{i}',
        'name': gate_name,
        'type': 'n8n-nodes-base.code',
        'typeVersion': 1,
        'position': [router_pos[0] + 200, router_pos[1] + i * 80 - 400],
        'parameters': {
            'mode': 'runOnceForAllItems',
            'language': 'javascript',
            'jsCode': gate_code
        }
    }
    nodes.append(gate_node)
    
    # Update Router connection: target -> gate node
    for conn in router_conns[0]:
        if conn['node'] == target:
            conn['node'] = gate_name
            break
    
    # Connect gate -> actual target
    conns[gate_name] = {'main': [[{'node': target, 'type': 'main', 'index': 0}]]}
    print(f'Added {gate_name} before {target}')

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
r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': v}, timeout=60)
print(f'Activate: {r4.status_code}')
if not r4.ok:
    print('Error:', r4.json().get('message', r4.text)[:500])

# Verify
total = len(wf2.get('nodes', []))
print(f'Total nodes: {total}')

# Check one gate
for n in wf2.get('nodes', []):
    if 'Gate' in n.get('name', ''):
        code = n.get('parameters', {}).get('jsCode', '')
        if '$input' in code:
            print(f'{n["name"]}: $input PRESERVED')
        break

s.close()
