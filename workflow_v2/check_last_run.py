"""Check last execution where Start Welcome actually ran"""
import requests, sys, json
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)
V2_ID = 'oV8dWIoAUHRkLaSb'

r = s.get(f'{BASE}/rest/executions?workflowId={V2_ID}&limit=10')
data = r.json()
results = data.get('data', data).get('results', [])

# Find executions where Start Welcome ran (more than just the 4 polling nodes)
for ex in results:
    ex_id = ex.get('id')
    status = ex.get('status')
    started = ex.get('startedAt', '')
    mode = ex.get('mode', '')

    r2 = s.get(f'{BASE}/rest/executions/{ex_id}')
    text = r2.text

    # Check if Start Welcome or more nodes are in this execution
    if 'Start Welcome' in text or 'Upsert User' in text or len(text) > 3000:
        print(f'\nExecution {ex_id}: status={status}, mode={mode}, started={started}')
        print(f'Contains Start Welcome: {"Start Welcome" in text}')
        print(f'Contains Upsert User: {"Upsert User" in text}')
        print(f'Contains error: {"error" in text.lower()}')
        print(f'Raw length: {len(text)}')

        # Show any error messages
        if 'error' in text.lower():
            # Try to extract error
            try:
                detail = r2.json()
                # Navigate the compact format for errors
                print(json.dumps(detail, ensure_ascii=False)[:2000])
            except:
                print(text[:2000])
        else:
            print(text[:1000])
        break
else:
    print('No executions found with Start Welcome')
    # Show last 3 executions at least
    for ex in results[:3]:
        print(f'Execution {ex.get("id")}: status={ex.get("status")}, mode={ex.get("mode")}, started={ex.get("startedAt")}')

s.close()
