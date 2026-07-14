// ============================================
// NODE: Router
// Type: Switch (mode: expression, outputs: 26)
// Reads user state from Supabase response, routes to correct branch
// ============================================

(() => {
  const text = String($json.message?.text || '').trim();
  const cb   = String($json.callback_query?.data || '');
  const hasPhoto = Array.isArray($json.message?.photo) && $json.message.photo.length > 0;
  const hasDocument = !!$json.message?.document;
  const hasContact = !!$json.message?.contact?.phone_number;
  const phoneLike = /^\+?\d[\d\s\-()]{8,}$/.test(text);

  const fromId = String(
    $json.message?.from?.id ||
    $json.callback_query?.from?.id ||
    ''
  );

  const adminId = String($json.app_config?.ADMIN_USER_ID || '7260765133');
  const crm = $json.crm || {};
  const state = String(crm.state || 'new');

  // 0 — /start
  if (text.startsWith('/start')) return 0;

  // 1 — Start purchase flow (QR, button, "Получить бонусы")
  if (cb === 'START_PURCHASE' || cb === 'START_FLOW' || text === '🎁 Получить бонусы') return 1;

  // 2 — Subscription confirmed
  if (cb === 'SUB_CONFIRMED') return 2;

  // 3 — Contact received (via Telegram share button)
  if (hasContact) return 3;

  // 4/5/6 — Package selection (3 options, matched by text)
  if (text === '1 варежка (3000 руб.)')        return 4;
  if (text === '1+2 варежки (7000 руб.)')       return 5;
  if (text === 'VIP: 1+2+5 варежек (11000 руб.)') return 6;

  // 7 — Photo uploaded
  if ((hasPhoto || hasDocument) && (state === 'awaiting_photo' || state === 'awaiting_purchase_photo')) return 7;

  // 8 — Admin manual approve (override, rare) — NOT auto-approve path
  if (cb.startsWith('APPROVE_PURCHASE|') || cb.startsWith('APPROVE|')) return 8;

  // 9 — Admin manual reject
  if (cb.startsWith('REJECT_PURCHASE|') || cb.startsWith('REJECT|')) return 9;

  // 10 — Start review flow
  if (cb === 'START_REVIEW' || text === '⭐ Оставить отзыв') return 10;

  // 11 — Marketplace selected
  if (['MARKETPLACE_WB', 'MARKETPLACE_OZON', 'MARKETPLACE_YM', 'MARKETPLACE_OTHER'].includes(cb)) return 11;

  // 12 — Review screenshot uploaded
  if ((hasPhoto || hasDocument) && state === 'awaiting_review_screenshot') return 12;

  // 13 — Review product photo uploaded
  if ((hasPhoto || hasDocument) && state === 'awaiting_review_product_photo') return 13;

  // 14 — Admin approve review
  if (cb.startsWith('APPROVE_REVIEW|')) return 14;

  // 15 — Admin reject review
  if (cb.startsWith('REJECT_REVIEW|')) return 15;

  // 16 — /status
  if (text === '📍 Мой статус' || text === '/status') return 16;

  // 17 — /back
  if (text === '⬅️ Назад' || text === '/back') return 17;

  // 18 — /continue
  if (text === '▶️ Продолжить' || text === '/continue') return 18;

  // 19 — /reset
  if (text === '🔄 Начать заново' || text === '/reset') return 19;

  // 20 — /help (also default fallback)
  if (text === '💬 Помощь' || text === '/help') return 20;

  // 21 — Admin: export CSV
  if (fromId === adminId && text === '/export_users') return 21;

  // 22 — Admin commands: /broadcast, /stats, /user
  if (fromId === adminId && (/^\/broadcast\b/.test(text) || text === '/stats' || /^\/user\b/.test(text))) return 22;

  // 23 — Upsell: yes
  if (cb === 'UPSELL_YES' || cb === 'BUY_UPSELL_STANDARD' || text === '🔥 Увеличить подарок') return 23;

  // 24 — Upsell: no
  if (cb === 'UPSELL_NO' || text === '❌ Нет, спасибо') return 24;

  // 25 — Phone entered as text (no contact button)
  if (!hasContact && phoneLike && state === 'awaiting_contact') return 25;

  // Default fallback → help
  return 20;
})()
