// ============================================
// NODE: Unified Followup
// Type: ScheduleTrigger (every 6h) → Code
// ============================================
// Replaces 9 separate nodes (cron + code + router + 6 Telegram).
// Queries users stuck in a state > threshold hours, sends reminder.
// Uses lookup table for message texts.
// ============================================

const config = $('App Config').first().json.app_config;

// Lookup: state → [threshold_hours, message_text, keyboard (optional)]
const followupConfig = {
  'awaiting_subscription': {
    hours: config.FOLLOWUP_SUBSCRIPTION_HOURS || 24,
    text: 'Вы не закончили оформление! Пожалуйста, подпишитесь на наш канал и нажмите «Проверить подписку».',
    keyboard: [ [{ text: '✅ Проверить подписку', callback_data: 'SUB_CONFIRMED' }] ]
  },
  'awaiting_contact': {
    hours: config.FOLLOWUP_CONTACT_HOURS || 24,
    text: 'Остался последний шаг! Поделитесь контактом чтобы продолжить.',
    keyboard: [ [{ text: '📱 Поделиться контактом', request_contact: true }] ]
  },
  'awaiting_package': {
    hours: config.FOLLOWUP_PACKAGE_HOURS || 48,
    text: 'Выберите ваш набор бонусов и получите подарки!',
    keyboard: [
      [{ text: '🧤 1 варежка (3000 руб.)',   callback_data: 'PACKAGE_STANDARD' }],
      [{ text: '🧤🧤 1+2 варежки (7000 руб.)', callback_data: 'PACKAGE_PREMIUM' }],
      [{ text: '👑 VIP: 1+2+5 (11000 руб.)',  callback_data: 'PACKAGE_VIP'    }]
    ]
  },
  'awaiting_photo': {
    hours: config.FOLLOWUP_PHOTO_HOURS || 48,
    text: 'Загрузите фото чека чтобы мы могли подтвердить покупку и выдать бонусы!',
    keyboard: null
  },
  'pending_approval': {
    hours: 6,
    text: 'Ваша заявка обрабатывается. Бонусы будут начислены автоматически. Ожидайте.',
    keyboard: null
  },
  'awaiting_review_marketplace': {
    hours: config.FOLLOWUP_REVIEW_HOURS || 72,
    text: 'Оставьте отзыв и получите дополнительные бонусы! Выберите маркетплейс:',
    keyboard: [
      [{ text: '🟣 Wildberries', callback_data: 'MARKETPLACE_WB' }],
      [{ text: '🟠 Ozon',        callback_data: 'MARKETPLACE_OZON' }],
      [{ text: '🟡 Яндекс',      callback_data: 'MARKETPLACE_YM' }]
    ]
  },
  'awaiting_upsell': {
    hours: config.FOLLOWUP_UPSELL_HOURS || 72,
    text: 'Увеличьте ваш набор бонусов со скидкой!',
    keyboard: [
      [{ text: '🔥 Увеличить подарок', callback_data: 'UPSELL_YES' }],
      [{ text: '❌ Нет, спасибо',      callback_data: 'UPSELL_NO'  }]
    ]
  }
};

// For each state, find users who are stuck
const results = [];
const now = new Date();

for (const [state, cfg] of Object.entries(followupConfig)) {
  const cutoff = new Date(now - cfg.hours * 60 * 60 * 1000).toISOString();

  // Find users: in this state, last_seen older than threshold, no recent followup
  const query = await $('Supabase Call').execute({
    table: 'users',
    method: 'GET',
    filter: `user_state=eq.${state}&last_seen=lte.${cutoff}&select=*&limit=50`
  });

  const users = query.first().json.rows || [];

  for (const user of users) {
    // Skip if followup already sent recently
    if (user.last_followup_at) {
      const lastFollowup = new Date(user.last_followup_at);
      const hoursSinceLast = (now - lastFollowup) / (1000 * 60 * 60);
      if (hoursSinceLast < cfg.hours) continue;
    }

    // Mark followup sent
    await $('Supabase Call').execute({
      table: 'users',
      method: 'PATCH',
      filter: `telegram_id=eq.${user.telegram_id}`,
      body: { last_followup_at: now.toISOString() }
    });

    // Log event
    await $('Supabase Call').execute({
      table: 'events',
      method: 'POST',
      body: {
        user_id: user.telegram_id,
        event_name: 'followup_sent',
        payload: { state: state }
      }
    });

    results.push({
      chatId: user.telegram_id,
      text: cfg.text,
      keyboard: cfg.keyboard || undefined
    });
  }
}

// Return all users to message. Telegram node downstream loops through them.
return results.length > 0
  ? results.map(r => ({ json: r }))
  : [{ json: { done: true, sent: 0, message: 'No followups needed' } }];
