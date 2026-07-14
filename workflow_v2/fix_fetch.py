import requests, json, sys, re
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)
V2_ID = 'oV8dWIoAUHRkLaSb'

r = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf = r.json().get('data', r.json())
nodes = wf.get('nodes', [])

fixed_count = 0

for node in nodes:
    if node.get('type') != 'n8n-nodes-base.code':
        continue

    code = node.get('parameters', {}).get('jsCode', '')
    name = node.get('name', '')

    if 'fetch(' not in code:
        continue

    # Replace all fetch calls with this.helpers.httpRequest
    # Pattern 1: await fetch(url, { headers }) — GET request
    # Pattern 2: await fetch(url, { method: "PATCH", headers, body: ... })
    # Pattern 3: await fetch(url, { method: "POST", headers, body: ... })

    # Strategy: add a helper function at the beginning of each code
    # that wraps this.helpers.httpRequest to be fetch-compatible

    helper = """// fetch polyfill using n8n's built-in HTTP helper
async function fetch(url, opts = {}) {
  const options = { url, method: opts.method || 'GET', headers: opts.headers || {} };
  if (opts.body) options.body = typeof opts.body === 'string' ? JSON.parse(opts.body) : opts.body;
  const result = await this.helpers.httpRequest(options);
  return { status: 200, ok: true, json: async () => result, text: async () => JSON.stringify(result) };
}

"""

    # Check if helper already added
    if 'fetch polyfill' not in code:
        # Add helper after first line (which is usually a comment)
        lines = code.split('\n')
        # Find a good insertion point - after the first // comment or H/header var
        insert_at = 0
        for i, line in enumerate(lines):
            if line.strip().startswith('//') or line.strip().startswith('const appConfig') or line.strip().startswith('const input'):
                insert_at = i + 1
                break
        if insert_at == 0:
            insert_at = 1

        lines.insert(insert_at, helper)
        code = '\n'.join(lines)
        node['parameters']['jsCode'] = code
        fixed_count += 1
        print(f'Fixed: {name}')

print(f'\nTotal fixed: {fixed_count} nodes')

# Upload
r2 = s.patch(f'{BASE}/rest/workflows/{V2_ID}', json={'nodes': nodes})
print(f'Update: {r2.status_code}')

# Reactivate
r3 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf2 = r3.json().get('data', r3.json())
version_id = wf2.get('versionId')
r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': version_id}, timeout=60)
print(f'Activate: {r4.status_code}')
if not r4.ok:
    print('Error:', r4.json().get('message', r4.text)[:500])
s.close()
