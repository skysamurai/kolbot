// ============================================
// NODE: Upsert User
// Type: Code
// Runs right after Router, before any branch.
// Loads or creates user record, attaches CRM to event.
// ============================================
// Replaces staticData pattern — now reads/writes Supabase

const config = $('App Config').first().json.app_config;
const input = $input.first().json;

// Extract user info from Telegram event
const msg = input.message || {};
const cb  = input.callback_query || {};
const from = msg.from || cb.from || {};
const telegramId = String(from.id || '');
const username   = from.username || '';
const firstName  = from.first_name || '';
const lastName   = from.last_name || '';

if (!telegramId) {
  return [{ json: { error: 'No telegram_id', crm: { state: 'new' } } }];
}

// Try to GET existing user
const getResult = await $('Supabase Call').execute({
  table: 'users',
  method: 'GET',
  filter: `telegram_id=eq.${telegramId}&select=*`
});

const existingUser = getResult.first().json.row;
const now = new Date().toISOString();

let user;
if (existingUser) {
  // Update last_seen
  user = existingUser;
  // Fire-and-forget: update last_seen
  await $('Supabase Call').execute({
    table: 'users',
    method: 'PATCH',
    filter: `telegram_id=eq.${telegramId}`,
    body: { last_seen: now }
  });
} else {
  // Create new user
  const createResult = await $('Supabase Call').execute({
    table: 'users',
    method: 'POST',
    body: {
      telegram_id: telegramId,
      username: username,
      first_name: firstName,
      last_name: lastName,
      user_state: 'new',
      bonus_access: 'locked',
      last_seen: now
    },
    upsert: true,
    onConflict: 'telegram_id'
  });
  user = createResult.first().json.row || {};
}

// Build CRM (user context) for router branches
const crm = {
  telegram_id: telegramId,
  state: user.user_state || 'new',
  purchase_status: user.purchase_status || null,
  bonus_access: user.bonus_access || 'locked',
  selected_package: user.selected_package || null,
  phone: user.phone || null,
  username: username,
  first_name: firstName
};

return [{
  json: {
    ...input,
    crm: crm,
    user: user,
    telegram_id: telegramId,
    raw: input.raw || input
  }
}];
