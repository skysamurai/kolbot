"""Check execution details more thoroughly"""
import requests, sys, json
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)
V2_ID = 'oV8dWIoAUHRkLaSb'

r = s.get(f'{BASE}/rest/executions?workflowId={V2_ID}&limit=3')
data = r.json()
results = data.get('data', data).get('results', [])

for ex in results[:2]:
    ex_id = ex.get('id')
    status = ex.get('status')
    started = ex.get('startedAt', '')
    print(f'\nExecution {ex_id}: status={status}, started={started}')

    r2 = s.get(f'{BASE}/rest/executions/{ex_id}')
    ex_detail = r2.json()

    # Try to get runData
    ed = ex_detail.get('data', ex_detail).get('executionData', {})
    if not ed:
        ed = ex_detail.get('data', ex_detail)

    run_data = ed.get('resultData', ed).get('runData', {})
    if not run_data:
        # Try other paths
        for key in ['executionData', 'resultData', 'workflowData']:
            nested = ex_detail.get('data', {}).get(key, {})
            rd = nested.get('runData', {})
            if rd:
                run_data = rd
                break

    print(f'  Nodes executed: {list(run_data.keys())[:10]}')

    for node_name, node_runs in run_data.items():
        for run in node_runs:
            console_output = ''
            exec_data = run.get('data', {})
            if isinstance(exec_data, dict):
                console_output = exec_data.get('console', '')
            elif isinstance(exec_data, list):
                for item in exec_data:
                    if isinstance(item, dict) and item.get('console'):
                        console_output = item['console']
                        break

            if console_output:
                print(f'  [{node_name}] console: {str(console_output)[:400]}')

            error_msg = ''
            if isinstance(exec_data, dict):
                error_msg = exec_data.get('error', '')
            if error_msg:
                print(f'  [{node_name}] ERROR: {str(error_msg)[:400]}')

    # Also try the full execution JSON for debugging
    break  # Just check the latest

# Also dump raw structure for debugging
print('\n\n--- RAW STRUCTURE of latest execution (first 2000 chars) ---')
ex_id = results[0].get('id') if results else None
if ex_id:
    r3 = s.get(f'{BASE}/rest/executions/{ex_id}')
    print(r3.text[:2000])

s.close()
