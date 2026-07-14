"""Extract error from execution 3259"""
import requests, sys, json, re
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)
V2_ID = 'oV8dWIoAUHRkLaSb'

r = s.get(f'{BASE}/rest/executions/3259')
text = r.text

# The format is: ["compressed_string", "decompressed_value", ...]
# We need to decompress it. Look for patterns.
# n8n uses a simple compression: repeated values are stored as numbers in
# the main array, and the actual values are at those indices.

try:
    data = r.json()
    comp = data['data']['data']
    # comp is a JSON string that's an array
    arr = json.loads(comp)

    # This is the n8n compact format: the array contains sections
    # Section 0: metadata (version, keys)
    # Section 1: {}
    # Section 2: {runData: ...}
    # Section 3: context data
    # ...

    # The runData is in index 4 (sometimes 2 or 3)
    # Let's find it
    print(f'Array has {len(arr)} sections')

    # Look for error strings
    for i, item in enumerate(arr):
        if isinstance(item, str) and 'error' in item.lower():
            print(f'Section {i}: {item[:500]}')
        elif isinstance(item, dict):
            for k, v in item.items():
                if isinstance(v, str) and 'error' in v.lower():
                    print(f'Section {i}, key {k}: {v[:500]}')

    # Also try to decompile the runData
    # The format is roughly:
    # arr[4] or arr[2] is {runData: ...} where the value is an index into arr
    for section_idx in [2, 3, 4, 10]:
        if section_idx < len(arr) and isinstance(arr[section_idx], dict):
            print(f'\nSection {section_idx}: {json.dumps(arr[section_idx], ensure_ascii=False)[:1000]}')

except Exception as e:
    print(f'Error parsing: {e}')
    # Just search for error in raw text
    for match in re.finditer(r'error[^"]{0,200}', text, re.IGNORECASE):
        print(match.group()[:300])

# Also check execution 3259 status now
r2 = s.get(f'{BASE}/rest/executions/3259')
try:
    status = r2.json().get('data', {}).get('status')
    print(f'\nCurrent status: {status}')
except:
    pass

s.close()
