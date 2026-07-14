// ============================================
// NODE: App Config
// Type: Code
// Position: right after Telegram Trigger
// ============================================
// Stores all configuration in one place.
// All other nodes read config from here via:
//   $('App Config').item.json.app_config

const normalizeBaseUrl = (value) => {
  const raw = String(value || '').trim();
  if (!raw) return '';
  return raw.replace(/\/rest\/v1\/?$/i, '').replace(/\/+$/, '');
};

// ⚠️ FILL REAL VALUES BEFORE DEPLOY
const supabaseUrl = normalizeBaseUrl('https://lzxdetxcipighlsyzjpi.supabase.co');
const supabaseKey = String('eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imx6eGRldHhjaXBpZ2hsc3l6anBpIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc3NzY0NjQ4MiwiZXhwIjoyMDkzMjIyNDgyfQ._QMn-mjdcDXfDH1BnuwLWZieH5gejcnAK4vkjnmRQEo').trim();
const subscriptionChannelId = String('@YourChannel').trim();
const managersGroupChatId = String('-1003989386408').trim();
const adminUserId = String('7260765133').trim();

// YooKassa
const ykShopId = String('YOUR_YOOKASSA_SHOP_ID').trim();
const ykSecret = String('YOUR_YOOKASSA_SECRET_KEY').trim();
const paymentReturnUrl = String('https://YOUR_DOMAIN/thanks').trim();

// Auto-approve timer (hours)
const autoApproveDelayHours = 1;

const config = {
  SUPABASE_URL: supabaseUrl,
  SUPABASE_REST_URL: supabaseUrl ? `${supabaseUrl}/rest/v1` : '',
  SUPABASE_SERVICE_ROLE_KEY: supabaseKey,
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

  // Followup thresholds (hours)
  FOLLOWUP_SUBSCRIPTION_HOURS: 24,
  FOLLOWUP_CONTACT_HOURS: 24,
  FOLLOWUP_PACKAGE_HOURS: 48,
  FOLLOWUP_PHOTO_HOURS: 48,
  FOLLOWUP_REVIEW_HOURS: 72,
  FOLLOWUP_UPSELL_HOURS: 72,

  WARMUP_ENABLED: true
};

const input = $input.first()?.json || {};

return [{
  json: {
    ...input,
    ...config,
    app_config: config,
    raw: input.raw || input
  }
}];
