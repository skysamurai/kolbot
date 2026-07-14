import requests, sys, time, re
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)
V2_ID = 'oV8dWIoAUHRkLaSb'

def test_config(desc, n_outputs, expr):
    s.post(f'{BASE}/rest/workflows/{V2_ID}/deactivate', timeout=30)
    
    r = s.get(f'{BASE}/rest/workflows/{V2_ID}')
    wf = r.json().get('data', r.json())
    nodes = wf.get('nodes', [])
    
    for node in nodes:
        if node.get('name') == 'Router':
            node['parameters'] = {
                "mode": "expression",
                "numberOutputs": n_outputs,
                "output": expr
            }
    
    s.patch(f'{BASE}/rest/workflows/{V2_ID}', json={'nodes': nodes})
    
    r3 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
    wf2 = r3.json().get('data', r3.json())
    version_id = wf2.get('versionId')
    s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': version_id}, timeout=60)
    
    time.sleep(8)
    
    # Check latest 3 executions
    r5 = s.get(f'{BASE}/rest/executions?workflowId={V2_ID}&limit=3')
    results = r5.json().get('data', {}).get('results', [])
    
    for ex in results[:1]:
        eid = ex['id']
        r6 = s.get(f'{BASE}/rest/executions/{eid}')
        raw = r6.text
        if 'Cannot read properties of undefined' in raw:
            print(f'{desc}: CRASH')
            return False
        else:
            print(f'{desc}: OK (status={ex["status"]})')
            return True

# Test 1: Hardcoded "0" with 26 outputs
test_config('Hardcoded "0" + 26 outs', 26, "0")

# Test 2: Simple $json._route with 2 outputs
test_config('$json._route + 2 outs', 2, "(() => { const r = $json._route; return (typeof r === 'number' && r >= 0 && r < 2) ? r : 0; })()")

# Test 3: Simple $json._route with 26 outputs 
test_config('$json._route + 26 outs', 26, "(() => { const r = $json._route; return (typeof r === 'number' && r >= 0 && r < 26) ? r : 0; })()")

s.close()
