import requests, sys, json
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)
V2_ID = 'oV8dWIoAUHRkLaSb'

r = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf = r.json().get('data', r.json())
nodes = wf.get('nodes', [])

# 1. Rewrite App Config with routing logic built-in
app_config_code = '''// NODE: App Config + Router
// Stores config AND determines route for downstream Switch

const normalizeBaseUrl = (value) => {
  const raw = String(value || '').trim();
  if (!raw) return '';
  return raw.replace(/\\/rest\\/v1\\/?$/i, '').replace(/\\/+$/, '');
};

const supabaseUrl = normalizeBaseUrl('https://lzxdetxcipighlsyzjpi.supabase.co');
const supabaseKey = String('eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx6eGRldHhjaXBpZ2hsc3l6anBpIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NzY0NjQ4MiwiZXhwIjoyMDkzMjIyNDgyfQ._QMn-mjdcDXfDH1BnuwLWZieH5gejcnAK4vkjnmRQEo').trim();
const botToken = String('8589709724:AAF8R-tki276jyAw69b1EhAEm2hp-5E2j_I').trim();
const subscriptionChannelId = String('@ch_spa').trim();
const managersGroupChatId = String('-1003989386408').trim();
const adminUserId = String('7260765133').trim();

const ykShopId = String('YOUR_YOOKASSA_SHOP_ID').trim();
const ykSecret = String('YOUR_YOOKASSA_SECRET_KEY').trim();
const paymentReturnUrl = String('https://YOUR_DOMAIN/thanks').trim();
const autoApproveDelayHours = 1;

const config = {
  SUPABASE_URL: supabaseUrl,
  SUPABASE_REST_URL: supabaseUrl ? `${supabaseUrl}/rest/v1` : '',
  SUPABASE_SERVICE_ROLE_KEY: supabaseKey,
  TELEGRAM_BOT_TOKEN: botToken,
  SUPABASE_CONFIGURED: !!(
    supabaseUrl && !supabaseUrl.includes('YOUR_PROJECT') &&
    supabaseKey && !supabaseKey.includes('YOUR_SUPABASE')
  ),
  SUBSCRIPTION_CHANNEL_ID: subscriptionChannelId,
  MANAGERS_GROUP_CHAT_ID: managersGroupChatId,
  ADMIN_USER_ID: adminUserId,
  PAYMENT_PROVIDER: 'yookassa',
  YOOKASSA_SHOP_ID: ykShopId,
  YOOKASSA_SECRET_KEY: ykSecret,
  PAYMENT_RETURN_URL: paymentReturnUrl,
  PAYMENT_CURRENCY: 'RUB',
  PAYMENTS_CONFIGURED: !!(
    ykShopId && !ykShopId.includes('YOUR_YOOKASSA') &&
    ykSecret && !ykSecret.includes('YOUR_YOOKASSA') &&
    paymentReturnUrl && !paymentReturnUrl.includes('YOUR_DOMAIN')
  ),
  AUTO_APPROVE_DELAY_HOURS: autoApproveDelayHours,
  AUTO_APPROVE_DELAY_MS: autoApproveDelayHours * 60 * 60 * 1000,
  FOLLOWUP_SUBSCRIPTION_HOURS: 24,
  FOLLOWUP_CONTACT_HOURS: 24,
  FOLLOWUP_PACKAGE_HOURS: 48,
  FOLLOWUP_PHOTO_HOURS: 48,
  FOLLOWUP_REVIEW_HOURS: 72,
  FOLLOWUP_UPSELL_HOURS: 72,
  WARMUP_ENABLED: true
};

const first = $input.first();
if (!first) { return []; }
const input = first.json || {};

// ---- ROUTING LOGIC ----
const msg = input.message || {};
const cb  = input.callback_query || {};
const text = String(msg.text || '').trim();
const cbData = String(cb.data || '');
const hasPhoto = Array.isArray(msg.photo) && msg.photo.length > 0;
const hasDocument = !!msg.document;
const hasContact = !!msg.contact?.phone_number;
const crm = input.crm || {};
const state = String(crm.state || 'new');
const fromId = String(msg.from?.id || cb.from?.id || '');
const adminId = String(config.ADMIN_USER_ID || '7260765133');

let route = 0;

if (text.startsWith('/start')) {
  route = 0;
} else if (cbData === 'START_PURCHASE' || cbData === 'START_FLOW' || text === '🎁 Получить бонусы') {
  route = 1;
} else if (cbData === 'SUB_CONFIRMED') {
  route = 2;
} else if (hasContact) {
  route = 3;
} else if (text === '1 варежка (3000 руб.)') {
  route = 4;
} else if (text === '1+2 варежки (7000 руб.)') {
  route = 5;
} else if (text === 'VIP: 1+2+5 варежек (11000 руб.)') {
  route = 6;
} else if ((hasPhoto || hasDocument) && (state === 'awaiting_photo' || state === 'awaiting_purchase_photo')) {
  route = 7;
} else if (cbData.startsWith('APPROVE_PURCHASE|') || cbData.startsWith('APPROVE|')) {
  route = 8;
} else if (cbData.startsWith('REJECT_PURCHASE|') || cbData.startsWith('REJECT|')) {
  route = 9;
} else if (cbData === 'START_REVIEW' || text === '⭐ Оставить отзыв') {
  route = 10;
} else if (['MARKETPLACE_WB', 'MARKETPLACE_OZON', 'MARKETPLACE_YM', 'MARKETPLACE_OTHER'].includes(cbData)) {
  route = 11;
} else if ((hasPhoto || hasDocument) && state === 'awaiting_review_screenshot') {
  route = 12;
} else if ((hasPhoto || hasDocument) && state === 'awaiting_review_product_photo') {
  route = 13;
} else if (cbData.startsWith('APPROVE_REVIEW|')) {
  route = 14;
} else if (cbData.startsWith('REJECT_REVIEW|')) {
  route = 15;
} else if (text === '📌 Мой статус') {
  route = 16;
} else if (cbData === 'BACK_TO_MAIN' || text === '🔙 Назад') {
  route = 17;
} else if (cbData === 'CONTINUE' || text === '▶️ Продолжить') {
  route = 18;
} else if (cbData === 'RESET_STATE' || text === '🔄 Сбросить') {
  route = 19;
} else if (cbData === 'HELP' || text === '❇️ Помощь') {
  route = 20;
} else if (cbData === 'ADMIN_EXPORT' && fromId === adminId) {
  route = 21;
} else if (text.startsWith('/admin') && fromId === adminId) {
  route = 22;
} else if (cbData === 'UPSELL_YES') {
  route = 23;
} else if (cbData === 'UPSELL_NO') {
  route = 24;
} else if (/^\\+?\\d[\\d\\s\\-()]{8,}$/.test(text)) {
  route = 25;
}

return [{
  json: {
    ...input,
    ...config,
    app_config: config,
    _route: route,
    raw: input.raw || input
  }
}];'''

for node in nodes:
    if node.get('name') == 'App Config':
        node['parameters']['jsCode'] = app_config_code
        print('Rewrote App Config with routing logic')

# 2. Simplify Router to just read _route
for node in nodes:
    if node.get('name') == 'Router':
        node['type'] = 'n8n-nodes-base.switch'
        node['typeVersion'] = 1
        node['parameters'] = {
            "mode": "expression",
            "numberOutputs": 26,
            "output": "(() => { const r = $json._route; return (typeof r === 'number' && r >= 0 && r < 26) ? r : 0; })()"
        }
        print('Simplified Router expression to read _route')

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
else:
    print('Workflow activated!')

# Verify
for n in wf2.get('nodes', []):
    if n.get('name') == 'App Config':
        code = n.get('parameters', {}).get('jsCode', '')
        if '_route' in code and 'if (!first)' in code:
            print('VERIFIED: App Config has routing + empty guard')
    if n.get('name') == 'Router':
        expr = n.get('parameters', {}).get('output', '')
        if '_route' in expr:
            print(f'VERIFIED: Router reads _route ({len(expr)} chars)')

s.close()
