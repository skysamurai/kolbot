import requests, sys, json
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)
V2_ID = 'oV8dWIoAUHRkLaSb'

r = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf = r.json().get('data', r.json())
nodes = wf.get('nodes', [])

# Build 26 rules for the Switch V1 in rules mode
# Each rule maps to one output
rules = [
    # 0 - /start
    {"value": "={{ String($json.message?.text || '').trim().startsWith('/start') }}", "output": 0},
    # 1 - Start purchase flow
    {"value": "={{ ['START_PURCHASE','START_FLOW'].includes($json.callback_query?.data) || String($json.message?.text || '').trim() === '🎁 Получить бонусы' }}", "output": 1},
    # 2 - Subscription confirmed
    {"value": "={{ $json.callback_query?.data === 'SUB_CONFIRMED' }}", "output": 2},
    # 3 - Contact received
    {"value": "={{ !!$json.message?.contact?.phone_number }}", "output": 3},
    # 4/5/6 - Package selection
    {"value": "={{ String($json.message?.text || '').trim() === '1 варежка (3000 руб.)' }}", "output": 4},
    {"value": "={{ String($json.message?.text || '').trim() === '1+2 варежки (7000 руб.)' }}", "output": 5},
    {"value": "={{ String($json.message?.text || '').trim() === 'VIP: 1+2+5 варежек (11000 руб.)' }}", "output": 6},
    # 7 - Photo uploaded
    {"value": "={{ (Array.isArray($json.message?.photo) && $json.message.photo.length > 0 || !!$json.message?.document) && ['awaiting_photo','awaiting_purchase_photo'].includes($json.crm?.state || '') }}", "output": 7},
    # 8 - Admin manual approve
    {"value": "={{ String($json.callback_query?.data || '').startsWith('APPROVE_PURCHASE|') || String($json.callback_query?.data || '').startsWith('APPROVE|') }}", "output": 8},
    # 9 - Admin manual reject
    {"value": "={{ String($json.callback_query?.data || '').startsWith('REJECT_PURCHASE|') || String($json.callback_query?.data || '').startsWith('REJECT|') }}", "output": 9},
    # 10 - Start review flow
    {"value": "={{ $json.callback_query?.data === 'START_REVIEW' || String($json.message?.text || '').trim() === '⭐ Оставить отзыв' }}", "output": 10},
    # 11 - Marketplace selected
    {"value": "={{ ['MARKETPLACE_WB','MARKETPLACE_OZON','MARKETPLACE_YM','MARKETPLACE_OTHER'].includes($json.callback_query?.data) }}", "output": 11},
    # 12 - Review screenshot uploaded
    {"value": "={{ (Array.isArray($json.message?.photo) && $json.message.photo.length > 0 || !!$json.message?.document) && ($json.crm?.state || '') === 'awaiting_review_screenshot' }}", "output": 12},
    # 13 - Review product photo uploaded
    {"value": "={{ (Array.isArray($json.message?.photo) && $json.message.photo.length > 0 || !!$json.message?.document) && ($json.crm?.state || '') === 'awaiting_review_product_photo' }}", "output": 13},
    # 14 - Admin approve review
    {"value": "={{ String($json.callback_query?.data || '').startsWith('APPROVE_REVIEW|') }}", "output": 14},
    # 15 - Admin reject review
    {"value": "={{ String($json.callback_query?.data || '').startsWith('REJECT_REVIEW|') }}", "output": 15},
    # 16 - /status
    {"value": "={{ String($json.message?.text || '').trim() === '📌 Мой статус' }}", "output": 16},
    # 17 - Back button
    {"value": "={{ $json.callback_query?.data === 'BACK_TO_MAIN' || String($json.message?.text || '').trim() === '🔙 Назад' }}", "output": 17},
    # 18 - Continue button
    {"value": "={{ $json.callback_query?.data === 'CONTINUE' || String($json.message?.text || '').trim() === '▶️ Продолжить' }}", "output": 18},
    # 19 - Reset
    {"value": "={{ $json.callback_query?.data === 'RESET_STATE' || String($json.message?.text || '').trim() === '🔄 Сбросить' }}", "output": 19},
    # 20 - Help
    {"value": "={{ $json.callback_query?.data === 'HELP' || String($json.message?.text || '').trim() === '❓ Помощь' }}", "output": 20},
    # 21 - Admin export
    {"value": "={{ $json.callback_query?.data === 'ADMIN_EXPORT' && $json.message?.from?.id == $json.app_config?.ADMIN_USER_ID }}", "output": 21},
    # 22 - Admin commands
    {"value": "={{ String($json.message?.text || '').startsWith('/admin') && $json.message?.from?.id == $json.app_config?.ADMIN_USER_ID }}", "output": 22},
    # 23 - Upsell Yes
    {"value": "={{ $json.callback_query?.data === 'UPSELL_YES' }}", "output": 23},
    # 24 - Upsell No
    {"value": "={{ $json.callback_query?.data === 'UPSELL_NO' }}", "output": 24},
    # 25 - Phone as text (fallback)
    {"value": "={{ /^\+?\d[\d\s\-()]{8,}$/.test(String($json.message?.text || '').trim()) }}", "output": 25},
]

# Build Router params
router_params = {
    "mode": "rules",
    "numberOutputs": 26,
    "rules": {
        "values": rules
    },
    "options": {}
}

# Update the Router node
for node in nodes:
    if node.get('name') == 'Router':
        node['parameters'] = router_params
        # Keep type as switch V1 (rules mode works in V1)
        print(f'Converted Router to rules mode with {len(rules)} rules')

# Upload
r2 = s.patch(f'{BASE}/rest/workflows/{V2_ID}', json={'nodes': nodes})
print(f'Update: {r2.status_code}')
if not r2.ok:
    print('Error:', r2.text[:1000])
    sys.exit(1)

# Deactivate/reactivate
r_deact = s.post(f'{BASE}/rest/workflows/{V2_ID}/deactivate', timeout=30)
print(f'Deactivate: {r_deact.status_code}')

r3 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf2 = r3.json().get('data', r3.json())
version_id = wf2.get('versionId')
r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': version_id}, timeout=60)
print(f'Activate: {r4.status_code}')
if not r4.ok:
    print('Error:', r4.json().get('message', r4.text)[:500])

# Verify Router
for n in wf2.get('nodes', []):
    if n.get('name') == 'Router':
        params = n.get('parameters', {})
        print(f'Mode: {params.get("mode")}')
        rules_count = len(params.get('rules', {}).get('values', []))
        print(f'Rules: {rules_count}')
        break

s.close()
