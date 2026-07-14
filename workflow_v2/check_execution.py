"""Check recent execution results"""
import requests, sys, json
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)
V2_ID = 'oV8dWIoAUHRkLaSb'

r = s.get(f'{BASE}/rest/executions?workflowId={V2_ID}&limit=5')
data = r.json()
results = data.get('data', data).get('results', [])

for ex in results:
    ex_id = ex.get('id')
    status = ex.get('status')
    started = ex.get('startedAt', '')
    stopped = ex.get('stoppedAt', '')
    print(f'Execution {ex_id}: status={status}, started={started}, stopped={stopped}')

    # Get execution details
    if status in ('success', 'error'):
        r2 = s.get(f'{BASE}/rest/executions/{ex_id}')
        ex_detail = r2.json()
        ex_data = ex_detail.get('data', ex_detail)
        workflow_data = ex_data.get('resultData', ex_data).get('data', ex_data)
        result_data = ex_data.get('resultData', {})

        # Check if Start Welcome ran
        task_data = result_data.get('resultData', result_data)
        run_data = ex_data.get('executionData', ex_data).get('resultData', ex_data).get('runData', {})
        for node_name, node_runs in run_data.items():
            if 'Welcome' in node_name or 'Start' in node_name:
                for run in node_runs:
                    console_output = run.get('data', {}).get('console', '')
                    if console_output:
                        print(f'  {node_name} console: {console_output[:300]}')
                    # Check for errors
                    err = run.get('data', {}).get('error', '')
                    if err:
                        print(f'  {node_name} ERROR: {str(err)[:300]}')
        break

s.close()
