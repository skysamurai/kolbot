// ============================================
// NODE: Save Photo & Create Submission
// Type: Code — branch 7
// ============================================
// User uploaded photo → create submission with anti-duplicate.
// Starts auto-approve timer (timer_started_at = now()).

const config = $('App Config').first().json.app_config;
const crm = $json.crm || {};

const photo = $json.message?.photo;
const document = $json.message?.document;
let fileId = '';

if (photo && Array.isArray(photo)) {
  // Get largest photo (last in array)
  fileId = photo[photo.length - 1].file_id;
} else if (document) {
  fileId = document.file_id;
}

if (!fileId) {
  return [{ json: { error: 'No photo or document found' } }];
}

// Anti-duplicate: try insert, expect unique constraint to reject duplicates
const insertResult = await $('Supabase Call').execute({
  table: 'submissions',
  method: 'POST',
  body: {
    user_id: crm.telegram_id,
    package: crm.selected_package || 'standard',
    photo_file_id: fileId,
    purchase_status: 'pending',
    timer_started_at: new Date().toISOString()
  },
  upsert: false
});

if (!insertResult.first().json.ok) {
  // Likely duplicate — user already has pending submission
  return [{
    json: {
      ...$json,
      duplicate: true,
      replyText: 'У вас уже есть заявка на модерации. Ожидайте одобрения.'
    }
  }];
}

// Update user state
await $('Supabase Call').execute({
  table: 'users',
  method: 'PATCH',
  filter: `telegram_id=eq.${crm.telegram_id}`,
  body: {
    user_state: 'pending_approval',
    purchase_status: 'pending'
  }
});

// Log event
await $('Supabase Call').execute({
  table: 'events',
  method: 'POST',
  body: {
    user_id: crm.telegram_id,
    event_name: 'submission_created',
    payload: {
      file_id: fileId,
      package: crm.selected_package
    }
  }
});

// Notify managers group (informational only, no action needed)
const notifyText = [
  '📸 <b>Новая заявка</b>',
  `├ Пользователь: <code>${crm.telegram_id}</code>`,
  `├ Пакет: ${crm.selected_package || 'standard'}`,
  `├ Статус: ожидает автоодобрения (через ${config.AUTO_APPROVE_DELAY_HOURS} ч.)`,
  `└ Время: ${new Date().toLocaleString('ru')}`
].join('\n');

return [{
  json: {
    ...$json,
    duplication: false,
    photoFileId: fileId,
    replyText: `✅ Фото получено!\n\nВаша заявка будет одобрена автоматически через ${config.AUTO_APPROVE_DELAY_HOURS} час.\nБонусы придут сразу после одобрения.`,
    notifyManagers: {
      chatId: config.MANAGERS_GROUP_CHAT_ID,
      text: notifyText,
      parse_mode: 'HTML'
    }
  }
}];
