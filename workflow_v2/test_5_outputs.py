import requests, sys, time
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)
V2_ID = 'oV8dWIoAUHRkLaSb'

def test_outputs(n):
    r = s.get(f'{BASE}/rest/workflows/{V2_ID}')
    wf = r.json().get('data', r.json())
    nodes = wf.get('nodes', [])
    
    for node in nodes:
        if node.get('name') == 'Router':
            node['parameters'] = {
                "mode": "expression",
                "numberOutputs": n,
                "output": "((r) => r < " + str(n) + " ? r : 0)($json._route || 0)"
            }
    
    r2 = s.patch(f'{BASE}/rest/workflows/{V2_ID}', json={'nodes': nodes})
    if not r2.ok:
        print(f'  Update failed: {r2.status_code}')
        return False
    
    r3 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
    wf2 = r3.json().get('data', r3.json())
    version_id = wf2.get('versionId')
    r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': version_id}, timeout=60)
    if not r4.ok:
        print(f'  Activate failed: {r4.status_code} - {r4.json().get("message", "")[:100]}')
        return False
    
    time.sleep(8)
    
    r5 = s.get(f'{BASE}/rest/executions?workflowId={V2_ID}&limit=3')
    results = r5.json().get('data', {}).get('results', [])
    
    for ex in results:
        if ex.get('status') in ('success', 'running'):
            print(f'  {n} outputs: WORKS! ({ex.get("status")})')
            return True
        elif ex.get('status') == 'error':
            r6 = s.get(f'{BASE}/rest/executions/{ex["id"]}')
            raw = r6.text
            if 'Cannot read properties' in raw:
                print(f'  {n} outputs: CRASHES (Cannot read push)')
                return False
            else:
                print(f'  {n} outputs: Different error')
                return False
    
    s.post(f'{BASE}/rest/workflows/{V2_ID}/deactivate', timeout=30)

# Test 5 outputs
test_outputs(5)
s.close()
