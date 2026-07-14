"""Find the execution that processed the /start command"""
import requests, sys, json, re
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)
V2_ID = 'oV8dWIoAUHRkLaSb'

# Get recent executions
r = s.get(f'{BASE}/rest/executions?workflowId={V2_ID}&limit=15')
data = r.json()
results = data.get('data', data).get('results', [])

print(f'Checking {len(results)} recent executions...\n')

for ex in results:
    ex_id = ex.get('id')
    status = ex.get('status')
    started = ex.get('startedAt', '')

    r2 = s.get(f'{BASE}/rest/executions/{ex_id}')
    text = r2.text

    # Check for Start Welcome or user messages
    has_welcome = 'Start Welcome' in text
    has_upsert = 'Upsert User' in text
    has_error = 'error' in text.lower()
    has_409 = '409' in text and 'conflict' in text.lower()

    # Check if this execution has message processing (more than just 4 polling nodes)
    # The 4 polling nodes are: Polling Cron, Prepare URL, Fetch Updates, Process Updates
    node_count = text.count('"name":"') + text.count("'name':'")

    print(f'Ex {ex_id}: status={status}, welcome={has_welcome}, upsert={has_upsert}, error={has_error}, 409={has_409}, started={started}')

    if has_welcome or has_error:
        # Show details
        if 'NodeApiError' in text:
            # Extract error
            match = re.search(r'NodeApiError: ([^"]+)', text)
            if match:
                print(f'  Error: {match.group(1)[:200]}')
        if '409' in text:
            print(f'  409 conflict detected')

s.close()
