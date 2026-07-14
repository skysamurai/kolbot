import requests, sys, json
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)
V2_ID = 'oV8dWIoAUHRkLaSb'

r = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf = r.json().get('data', r.json())
nodes = wf.get('nodes', [])

# 1. Fix App Config - don't produce output on empty input
for node in nodes:
    if node.get('name') == 'App Config':
        old_code = node['parameters']['jsCode']
        # Replace the last two lines to add empty-input guard
        old_end = '''const input = $input.first()?.json || {};

return [{
  json: {
    ...input,
    ...config,
    app_config: config,
    raw: input.raw || input
  }
}];'''
        new_end = '''const first = $input.first();
if (!first) { return []; }
const input = first.json || {};

return [{
  json: {
    ...input,
    ...config,
    app_config: config,
    raw: input.raw || input
  }
}];'''
        node['parameters']['jsCode'] = old_code.replace(old_end, new_end)
        print('Fixed App Config - stops on empty input')

# 2. Fix Router - add fallback return
for node in nodes:
    if node.get('name') == 'Router':
        old_expr = node['parameters']['output']
        # Find the closing of the IIFE and add fallback + proper closing
        # The expression ends with something like: return something; })()
        # Add 'return 0;' as last line inside the IIFE
        
        # Find the last condition check and add fallback before the closing
        # The expression is wrapped in (() => { ... })()
        # Add return 0; before the closing })()
        
        # Strategy: replace the last occurrence of a return statement or the IIFE closing
        lines = old_expr.split('\n')
        
        # Find the line with the closing '})()' pattern
        new_lines = []
        added_fallback = False
        for i, line in enumerate(lines):
            if not added_fallback and ('})()' in line or line.strip() == '})();'):
                # Add fallback before closing
                new_lines.append('')
                new_lines.append('  // Fallback - if nothing matched, route to /start')
                new_lines.append('  return 0;')
                new_lines.append('')
                added_fallback = True
            new_lines.append(line)
        
        if added_fallback:
            new_expr = '\n'.join(new_lines)
            node['parameters']['output'] = new_expr
            print('Fixed Router - added fallback return 0')
        else:
            print('WARNING: Could not find closing in Router expression')

# Upload
r2 = s.patch(f'{BASE}/rest/workflows/{V2_ID}', json={'nodes': nodes})
print(f'Update: {r2.status_code}')
if not r2.ok:
    print('Error:', r2.text[:500])
    sys.exit(1)

# Reactivate
r3 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf2 = r3.json().get('data', r3.json())
version_id = wf2.get('versionId')
r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': version_id}, timeout=60)
print(f'Activate: {r4.status_code}')
if not r4.ok:
    print('Error:', r4.json().get('message', r4.text)[:500])

# Verify
for n in wf2.get('nodes', []):
    name = n.get('name', '')
    if name == 'App Config':
        code = n.get('parameters', {}).get('jsCode', '')
        if 'if (!first)' in code:
            print('VERIFIED: App Config has empty-input guard')
    if name == 'Router':
        expr = n.get('parameters', {}).get('output', '')
        if 'return 0;' in expr and 'Fallback' in expr:
            print('VERIFIED: Router has fallback')

s.close()
