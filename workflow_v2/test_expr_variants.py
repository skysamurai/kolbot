import requests, sys, time
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)
V2_ID = 'oV8dWIoAUHRkLaSb'

def test(desc, n_outs, expr):
    s.post(f'{BASE}/rest/workflows/{V2_ID}/deactivate', timeout=30)
    r = s.get(f'{BASE}/rest/workflows/{V2_ID}')
    wf = r.json().get('data', r.json())
    nodes = wf.get('nodes', [])
    
    for node in nodes:
        if node.get('name') == 'Router':
            node['parameters'] = {
                "mode": "expression",
                "numberOutputs": n_outs,
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
        if 'Cannot read properties of undefined' in raw:
            print(f'{desc}: CRASH')
            return False
        else:
            print(f'{desc}: OK ({ex["status"]})')
            return True

# Try different expression formats to access _route
tests = [
    ("$item.json._route", 2, "(() => { try { return $item.json._route || 0; } catch(e) { return 0; } })()"),
    ("$json._route direct", 2, "$json._route"),
    ("parseInt trick", 2, "(() => { const v = parseInt(String($json._route)); return isNaN(v) ? 0 : v; })()"),
]

for desc, n, expr in tests:
    result = test(desc, n, expr)
    if result:
        # If this expression works, try with 26 outputs
        test(f'{desc} + 26 outs', 26, expr)

s.close()
