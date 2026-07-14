import requests, sys
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)
V2_ID = 'oV8dWIoAUHRkLaSb'

r = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf = r.json().get('data', r.json())
nodes = wf.get('nodes', [])

# Helper function that captures 'this' context properly
fetch_helper = """const _n8nThis = this;

async function fetch(url, opts) {
  opts = opts || {};
  const options = {
    url: url,
    method: opts.method || 'GET',
    headers: opts.headers || {}
  };
  if (opts.body) {
    try { options.body = JSON.parse(opts.body); } catch(e) { options.body = opts.body; }
  }
  const result = await _n8nThis.helpers.httpRequest(options);
  return {
    status: 200,
    ok: true,
    json: async function() { return result; },
    text: async function() { return JSON.stringify(result); }
  };
}
"""

fixed = 0
for node in nodes:
    if node.get('type') != 'n8n-nodes-base.code':
        continue

    code = node.get('parameters', {}).get('jsCode', '')
    name = node.get('name', '')

    # Skip if it doesn't use fetch or already has our helper
    if 'await fetch(' not in code and 'fetch(' not in code:
        continue
    if '_n8nThis' in code:
        continue  # already fixed

    # Remove old broken polyfill if present
    if 'fetch polyfill using n8n' in code:
        lines = code.split('\n')
        # Remove lines from '// fetch polyfill' to the closing '}\n' of the function
        new_lines = []
        skip = False
        for line in lines:
            if 'fetch polyfill' in line:
                skip = True
                continue
            if skip and line.strip() == '}' or (skip and line.strip() == '' and not skip):
                if line.strip() == '}':
                    skip = False
                    continue
            if not skip:
                new_lines.append(line)
        code = '\n'.join(new_lines)

    # Add our proper fetch polyfill
    lines = code.split('\n')
    # Insert after first line (usually a comment)
    insert_idx = 1
    for i, line in enumerate(lines):
        if i == 0:
            continue
        if line.strip() and not line.strip().startswith('//') and not line.strip().startswith('/*'):
            insert_idx = i
            break

    lines.insert(insert_idx, fetch_helper)
    code = '\n'.join(lines)
    node['parameters']['jsCode'] = code
    fixed += 1
    print(f'Fixed: {name}')

print(f'\nTotal fixed: {fixed} nodes')

# Upload
r2 = s.patch(f'{BASE}/rest/workflows/{V2_ID}', json={'nodes': nodes})
print(f'Update: {r2.status_code}')

# Verify one node
r3 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf2 = r3.json().get('data', r3.json())
for n in wf2.get('nodes', []):
    if n.get('name') == 'Upsert User':
        code = n.get('parameters', {}).get('jsCode', '')
        # Check $input is preserved
        if '$input' in code:
            print('$input PRESERVED in Upsert User')
        else:
            print('WARNING: $input MISSING from Upsert User!')
        # Check _n8nThis
        if '_n8nThis' in code:
            print('_n8nThis helper present')
        break

# Reactivate
version_id = wf2.get('versionId')
r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': version_id}, timeout=60)
print(f'Activate: {r4.status_code}')
if not r4.ok:
    print('Error:', r4.json().get('message', r4.text)[:500])

s.close()
