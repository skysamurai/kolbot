// ============================================
// NODE: Bonus Redirect Webhook
// Type: Webhook (GET) → Code
// Path: /r/:userId/:bonusKey
// ============================================
// Wraps all bonus links. Records click event, then 302 redirects to real URL.
// Called when user taps a bonus button.

const config = $('App Config').first().json.app_config;

// Parse params from webhook path
const params = $input.first().json.params || {};
const userId = String(params.userId || '').trim();
const bonusKey = String(params.bonusKey || '').trim();

if (!userId || !bonusKey) {
  return [{ json: { status: 400, body: 'Missing userId or bonusKey' } }];
}

// Get user to find their package
const userResult = await $('Supabase Call').execute({
  table: 'users',
  method: 'GET',
  filter: `telegram_id=eq.${userId}&select=selected_package`
});

const user = userResult.first().json.row;
if (!user || !user.selected_package) {
  return [{ json: { status: 404, body: 'User or package not found' } }];
}

// Get bonus info
const bonusResult = await $('Supabase Call').execute({
  table: 'bonuses',
  method: 'GET',
  filter: `package=eq.${user.selected_package}&bonus_key=eq.${bonusKey}&select=*`
});

const bonus = bonusResult.first().json.row;
if (!bonus || !bonus.real_url) {
  return [{ json: { status: 404, body: 'Bonus not found' } }];
}

// Log click event
await $('Supabase Call').execute({
  table: 'events',
  method: 'POST',
  body: {
    user_id: userId,
    event_name: 'bonus_clicked',
    payload: {
      package: user.selected_package,
      bonus_key: bonusKey,
      bonus_name: bonus.bonus_name,
      school_name: bonus.school_name
    }
  }
});

// HTTP 302 redirect to real bonus URL
return [{
  json: {
    status: 302,
    headers: {
      Location: bonus.real_url
    }
  }
}];
