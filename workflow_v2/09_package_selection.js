// ============================================
// NODE: Save Package (UNIFIED)
// Type: Code — replaces 3 separate nodes
// ============================================
// Called when user selects a package (branches 4/5/6).
// Lookup table in bonuses DB, not hardcoded.

const config = $('App Config').first().json.app_config;
const crm = $json.crm || {};

// Map text → package key
const textToPackage = {
  '1 варежка (3000 руб.)':        'standard',
  '1+2 варежки (7000 руб.)':       'premium',
  'VIP: 1+2+5 варежек (11000 руб.)': 'vip'
};

const packageKey = textToPackage[$json.message?.text] || crm.selected_package;

if (!packageKey) {
  return [{ json: { error: 'Unknown package' } }];
}

// Get package bonuses from DB (not hardcoded)
const bonusesResult = await $('Supabase Call').execute({
  table: 'bonuses',
  method: 'GET',
  filter: `package=eq.${packageKey}&is_active=eq.true&select=bonus_name,description`
});

const bonuses = bonusesResult.first().json.rows || [];

// Update user
await $('Supabase Call').execute({
  table: 'users',
  method: 'PATCH',
  filter: `telegram_id=eq.${crm.telegram_id}`,
  body: {
    selected_package: packageKey,
    user_state: 'awaiting_photo'
  }
});

// Log event
await $('Supabase Call').execute({
  table: 'events',
  method: 'POST',
  body: {
    user_id: crm.telegram_id,
    event_name: 'package_selected',
    payload: { package: packageKey }
  }
});

return [{
  json: {
    ...$json,
    package: packageKey,
    bonuses: bonuses,
    crm: { ...crm, state: 'awaiting_photo', selected_package: packageKey },
    // Message to user
    replyText: `Вы выбрали пакет «${packageKey}».\n\nВ него входят:\n${bonuses.map((b,i) => `${i+1}. ${b.bonus_name} — ${b.description || ''}`).join('\n')}\n\nТеперь загрузите фото чека.`
  }
}];
