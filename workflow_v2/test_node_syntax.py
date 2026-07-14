import requests, sys, time
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

# Try using $node reference instead of $json
tests = [
    "$node ref", "(() => { try { const r = $node['Upsert User'].data._route; return (typeof r === 'number') ? r : 0; } catch(e) { return 0; } })()",
    "item ref", "(() => { try { const r = $item.json._route; return (typeof r === 'number') ? r : 0; } catch(e) { return 0; } })()",
    "binary ref", "(() => { try { const r = $binary._route; return (typeof r === 'number') ? r : 0; } catch(e) { return 0; } })()",
]

for desc, expr in tests:
    s.post(f'{BASE}/rest/workflows/{V2_ID}/deactivate', timeout=30)
    r = s.get(f'{BASE}/rest/workflows/{V2_ID}')
    nodes = r.json().get('data', r.json()).get('nodes', [])
    
    for node in nodes:
        if node.get('name') == 'Router':
            node['type'] = 'n8n-nodes-base.switch'
            node['typeVersion'] = 1
            node['parameters'] = {
                "mode": "expression",
                "numberOutputs": 2,
                "output": expr
            }
    
    s.patch(f'{BASE}/rest/workflows/{V2_ID}', json={'nodes': nodes})
    r3 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
    wf2 = r3.json().get('data', r3.json())
    version_id = wf2.get('versionId')
    s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': version_id}, timeout=60)
    
    time.sleep(8)
    
    r5 = s.get(f'{BASE}/rest/executions?workflowId={V2_ID}&limit=2')
    results = r5.json().get('data', {}).get('results', [])
    
    for ex in results[:1]:
        eid = ex['id']
        r6 = s.get(f'{BASE}/rest/executions/{eid}')
        raw = r6.text
        if 'Cannot read properties of undefined' in raw and 'push' in raw:
            print(f'{desc}: SWITCH CRASH')
            break
        else:
            print(f'{desc}: OK ({ex["status"]})')
            break
    else:
        print(f'{desc}: no executions')

s.close()
