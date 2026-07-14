"""Extract Telegram node output from execution data to see what API response was"""
import requests, sys, json, re
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)
V2_ID = 'oV8dWIoAUHRkLaSb'

# Get recent executions
r = s.get(f'{BASE}/rest/executions?workflowId={V2_ID}&limit=20')
results = r.json().get('data', {}).get('results', [])

# Find the latest execution that's not "running" and might have processed a message
for ex in results:
    ex_id = ex.get('id')
    status = ex.get('status')
    if status == 'running':
        continue

    r2 = s.get(f'{BASE}/rest/executions/{ex_id}')
    text = r2.text

    # Check if this execution has Send Start Welcome in runData
    if '"Send Start Welcome"' not in text:
        continue

    print(f'Execution {ex_id}: status={status}')

    # The compressed format makes it hard to parse. Let me try to find the
    # data section for Send Start Welcome node
    # Look for patterns like: "Send Start Welcome":"NN" where NN is an index
    match = re.search(r'"Send Start Welcome":"(\d+)"', text)
    if match:
        data_idx = int(match.group(1))
        print(f'  Send Start Welcome data index: {data_idx}')

    # Try to find any error or result data related to this node
    # Look for error_code, description patterns (Telegram API error format)
    for pattern in [r'"error_code":\d+', r'"ok":(true|false)', r'"description":"[^"]*"']:
        matches = re.findall(pattern, text)
        if matches:
            print(f'  Found: {matches[:5]}')

    # Try to find the section that contains the Telegram API response
    # The decoded data would show what Telegram returned
    # Look for raw JSON around Send Start Welcome
    idx = text.find('Send Start Welcome')
    if idx >= 0:
        snippet = text[idx-50:idx+200]
        print(f'  Context: {snippet[:300]}')

    # Only check the most recent relevant execution
    break

s.close()
