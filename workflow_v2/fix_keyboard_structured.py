"""Fix keyboard: use top-level replyMarkup with structured inlineKeyboard"""
import requests, sys, json
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)
V2_ID = 'oV8dWIoAUHRkLaSb'

s.post(f'{BASE}/rest/workflows/{V2_ID}/deactivate', timeout=30)

r = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf = r.json().get('data', r.json())
nodes = wf.get('nodes', [])

# Define keyboard structure for each Code node's output
# We'll read what kb the Code node outputs and create matching structured keyboard
code_to_telegram = {
    'Start Welcome': 'Send Start Welcome',
    'Check Subscription': 'Send Check Sub',
    'Contact Request': 'Send Contact Request',
    'Package Choice': 'Send Package Choice',
    'Photo Received': 'Send Photo Received',
    'Package Standard': 'Send Pkg Standard',
    'Package Premium': 'Send Pkg Premium',
    'Package VIP': 'Send Pkg VIP',
    'Build Status': 'Send Status',
    'Build Back': 'Send Back',
    'Build Continue': 'Send Continue',
    'Reset State': 'Send Reset',
    'Help Message': 'Send Help',
    'Phone As Text': 'Send Phone Confirm',
    'Start Review': 'Send Review Start',
    'Save Marketplace': 'Send Ask Screenshot',
    'Save Rev Screenshot': 'Send Ask Prod Photo',
    'Save Rev Prod Photo': 'Send Rev Pending',
    'Admin Export': 'Send Export CSV',
    'Admin Commands': 'Send Admin Result',
    'Upsell Yes': 'Send Upsell Yes',
    'Upsell No': 'Send Upsell No',
    'Daily Report': 'Send Daily Report',
    'Payment Confirm': 'Send Payment Confirm',
    'Approve Purchase': 'Send Approve Purchase',
    'Reject Purchase': 'Send Reject Purchase',
    'Approve Review': 'Send Approve Review',
    'Reject Review': 'Send Reject Review',
    'Followup Messages': 'Send Followup Messages',
    'Approve Messages': 'Send Approve Messages',
}

# Extract kb object from Code node JS code
import re

def extract_kb_object(code):
    """Extract the inline keyboard object from Code node JS"""
    # Pattern: const kb = {"inline_keyboard": [...]};
    match = re.search(r'const kb = (\{[^;]+\});', code)
    if match:
        try:
            return json.loads(match.group(1))
        except:
            pass

    # Pattern: const kb = JSON.stringify(...) - not an object
    # Pattern: dynamic kb construction
    return None

def kb_object_to_structured(kb_obj):
    """Convert {inline_keyboard: [[{text, callback_data}]]} to n8n structured format"""
    inline_keyboard = kb_obj.get('inline_keyboard', [])
    rows = []
    for row_buttons in inline_keyboard:
        buttons = []
        for btn in row_buttons:
            btn_struct = {'text': btn.get('text', '')}
            af = {}
            if 'callback_data' in btn:
                af['callbackData'] = btn['callback_data']
            if 'url' in btn:
                af['url'] = btn['url']
            if af:
                btn_struct['additionalFields'] = af
            buttons.append(btn_struct)
        rows.append({'row': {'buttons': buttons}})

    return {
        'replyMarkup': 'inlineKeyboard',
        'inlineKeyboard': {'rows': rows}
    }

fixed_telegram = 0
fixed_code_nodes = 0

# First pass: extract kb objects from Code nodes
code_kbs = {}
for node in nodes:
    if node.get('type') != 'n8n-nodes-base.code':
        continue
    name = node.get('name', '')
    code = node.get('parameters', {}).get('jsCode', '')
    kb = extract_kb_object(code)
    if kb:
        code_kbs[name] = kb
        print(f'Code node "{name}": extracted kb with {len(kb.get("inline_keyboard", []))} rows')

# Second pass: apply structured keyboard to Telegram nodes
for node in nodes:
    if node.get('type') != 'n8n-nodes-base.telegram':
        continue
    tg_name = node.get('name', '')
    params = node.get('parameters', {})

    # Find the matching Code node by reverse lookup
    code_name = None
    for cn, tn in code_to_telegram.items():
        if tn == tg_name:
            code_name = cn
            break

    if not code_name or code_name not in code_kbs:
        continue

    kb_obj = code_kbs[code_name]
    structured = kb_object_to_structured(kb_obj)

    # Remove old additionalFields.reply_markup
    af = params.get('additionalFields', {})
    af.pop('reply_markup', None)
    if not af:
        params.pop('additionalFields', None)

    # Add top-level replyMarkup with structured keyboard
    params['replyMarkup'] = structured['replyMarkup']
    params['inlineKeyboard'] = structured['inlineKeyboard']

    fixed_telegram += 1
    print(f'Fixed keyboard: {tg_name}')

print(f'\nFixed {fixed_telegram} Telegram nodes with structured keyboards')
print(f'Found {len(code_kbs)} Code nodes with extractable inline_keyboard objects')

# Upload
r2 = s.patch(f'{BASE}/rest/workflows/{V2_ID}', json={'nodes': nodes})
print(f'Update: {r2.status_code}')
if not r2.ok:
    print('Error:', r2.text[:500])
    sys.exit(1)

# Verify
r3 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf2 = r3.json().get('data', r3.json())
for n in wf2.get('nodes', []):
    if n.get('name') == 'Send Start Welcome':
        params = n.get('parameters', {})
        print(f'\nVerification for Send Start Welcome:')
        print(f'  replyMarkup: {params.get("replyMarkup")}')
        ik = params.get('inlineKeyboard', {})
        rows = ik.get('rows', [])
        if rows:
            first_btn = rows[0].get('row', {}).get('buttons', [{}])[0]
            print(f'  First button: text="{first_btn.get("text")}", cb="{first_btn.get("additionalFields", {}).get("callbackData")}"')
        break

# Activate
v = wf2.get('versionId')
r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': v}, timeout=60)
print(f'Activate: {r4.status_code}')
if not r4.ok:
    print('Error:', r4.json().get('message', r4.text)[:500])

s.close()
