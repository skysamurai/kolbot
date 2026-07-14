// ============================================
// NODE: Cron — Auto-Approve Purchases
// Type: ScheduleTrigger → Code
// ============================================
// Runs every 5 minutes via Cron trigger.
// Finds submissions pending > 1 hour and auto-approves.
// Sends bonuses to user.

const config = $('App Config').first().json.app_config;
const delayMs = config.AUTO_APPROVE_DELAY_MS || 3600000; // 1 hour
const cutoff = new Date(Date.now() - delayMs).toISOString();

// Find submissions pending longer than threshold
const pending = await $('Supabase Call').execute({
  table: 'submissions',
  method: 'GET',
  filter: `purchase_status=eq.pending&timer_started_at=lte.${cutoff}&select=*`
});

const toApprove = pending.first().json.rows || [];

if (toApprove.length === 0) {
  return [{ json: { approved: 0, message: 'Nothing to approve' } }];
}

let approved = 0;
let failed = 0;

for (const sub of toApprove) {
  const userId = sub.user_id;

  // Approve submission
  const approveResult = await $('Supabase Call').execute({
    table: 'submissions',
    method: 'PATCH',
    filter: `id=eq.${sub.id}`,
    body: {
      purchase_status: 'approved',
      approved_at: new Date().toISOString()
    }
  });

  if (!approveResult.first().json.ok) {
    failed++;
    continue;
  }

  // Unlock bonuses for user
  await $('Supabase Call').execute({
    table: 'users',
    method: 'PATCH',
    filter: `telegram_id=eq.${userId}`,
    body: {
      purchase_status: 'approved',
      bonus_access: 'unlocked',
      user_state: 'approved'
    }
  });

  // Log event
  await $('Supabase Call').execute({
    table: 'events',
    method: 'POST',
    body: {
      user_id: userId,
      event_name: 'submission_approved',
      payload: {
        submission_id: sub.id,
        package: sub.package,
        auto: true
      }
    }
  });

  // Send bonus keyboard to user
  const bonusesResult = await $('Supabase Call').execute({
    table: 'bonuses',
    method: 'GET',
    filter: `package=eq.${sub.package}&is_active=eq.true&select=*`
  });

  const bonuses = bonusesResult.first().json.rows || [];
  const keyboard = {
    inline_keyboard: bonuses.map((b, i) => [{
      text: `🎁 ${b.bonus_name}`,
      url: `${config.PAYMENT_RETURN_URL}/r/${userId}/${b.bonus_key}`
    }])
  };

  // Send to user via Telegram
  // ⚠️ This needs Telegram node — n8n will handle the send
  // We just pass the data forward
  approved++;

  // We can only send one Telegram message per Code execution.
  // For bulk, we return all users and let a Telegram node loop.
  // Store the current one for the immediate send
  $json.toSend = {
    chatId: userId,
    text: `✅ Ваша заявка одобрена!\n\nВы выбрали пакет «${sub.package}».\nВот ваши бонусы:`,
    keyboard: keyboard
  };
  $json.allApproved = toApprove;
}

return [{
  json: {
    approved: approved,
    failed: failed,
    total: toApprove.length,
    toSend: toApprove[0]?.toSend,
    allApproved: toApprove
  }
}];
