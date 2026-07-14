"""Check which nodes actually RAN in recent executions"""
import requests, sys, json
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)
V2_ID = 'oV8dWIoAUHRkLaSb'

r = s.get(f'{BASE}/rest/executions?workflowId={V2_ID}&limit=5')
results = r.json().get('data', {}).get('results', [])

for ex in results:
    ex_id = ex.get('id')
    status = ex.get('status')

    r2 = s.get(f'{BASE}/rest/executions/{ex_id}')
    text = r2.text

    # n8n compresses execution data. Look for run data nodes.
    # The format has references like: {"Polling Cron":"12","Prepare URL":"13",...}
    # This section shows which nodes ran and their data references

    # Check which nodes are in the runData
    import re
    # Find the runData mapping: {"NodeName":"N","NodeName2":"N2",...}
    run_data_match = re.search(r'\{\"Polling Cron\"[^}]+Process Updates\"[^}]+}', text)
    if not run_data_match:
        run_data_match = re.search(r'\"Polling Cron\":\"[^\"]+\"', text)

    # Check if execution went beyond Process Updates
    has_process = 'Process Updates' in text
    has_app = 'App Config' in text
    has_upsert = 'Upsert User' in text
    has_welcome = 'Start Welcome' in text

    # More precise: check if these appear as executed nodes (not just workflow def)
    # In compressed format, executed nodes appear in the runData section
    # The runData section is between "runData":"4" and the next section
    # Actually nodes that run have data entries like:
    # {"startTime":...,"executionIndex":0,"source":[...],"executionStatus":"success","data":{...}}

    success_count = text.count('"executionStatus":"success"')
    error_count = text.count('"executionStatus":"error"')

    # Check for actual console output or error messages from nodes
    has_console = '"console"' in text

    print(f'Ex {ex_id}: status={status}, executed_nodes≈{success_count}, errors={error_count}, console={has_console}')

    # If this execution has few executed nodes, it's an empty poll
    # If it has many, a message was processed
    if success_count > 4:
        # Has more than just the 4 polling nodes
        print(f'  -> Message processed! ({success_count} nodes executed)')
        # Show any errors
        if error_count > 0:
            print(f'  -> HAS ERRORS!')
    elif success_count == 4:
        print(f'  -> Empty poll')
    else:
        print(f'  -> Unknown ({success_count} nodes)')

s.close()
