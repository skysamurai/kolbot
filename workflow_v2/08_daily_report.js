// ============================================
// NODE: Daily Conversion Report
// Type: ScheduleTrigger (daily at 09:00 MSK) → Code
// ============================================
// Queries view_conversion_summary, formats report, sends to managers group.
// ============================================

const config = $('App Config').first().json.app_config;

// Get conversion data from the pre-built view
const result = await $('Supabase Call').execute({
  table: 'view_conversion_summary',
  method: 'GET',
  filter: 'select=*'
});

const rows = result.first().json.rows || [];
const today = rows.find(r => r.period === 'today') || {};
const week = rows.find(r => r.period === 'week') || {};

// Calculate conversion rates
const calcRate = (numerator, denominator) => {
  if (!denominator || denominator === 0) return '—';
  return Math.round((numerator / denominator) * 100) + '%';
};

const reportText = [
  '📊 <b>CH-SPA — отчёт о конверсии</b>',
  '',
  `📅 <b>За вчера (${new Date(Date.now() - 86400000).toLocaleDateString('ru')})</b>`,
  `├ Стартов:              ${today.starts || 0}`,
  `├ Контактов оставили:   ${today.contacts || 0}`,
  `├ Выбрали пакет:        ${today.packages || 0}`,
  `├ Заявок создано:       ${today.submissions || 0}`,
  `├ Одобрено (авто):      ${today.approved || 0}`,
  `├ Кликов по бонусам:    ${today.bonus_clicks || 0}`,
  `├ Отзывов одобрено:     ${today.reviews || 0}`,
  `├ Оплат (upsell):       ${today.payments || 0}`,
  `└ Активных пользователей: ${today.active_users || 0}`,
  '',
  '<b>Конверсия за сегодня:</b>',
  `├ Старт → Контакт:      ${calcRate(today.contacts, today.starts)}`,
  `├ Старт → Заявка:       ${calcRate(today.submissions, today.starts)}`,
  `├ Заявка → Одобрение:   ${calcRate(today.approved, today.submissions)}`,
  `├ Одобрение → Клик:     ${calcRate(today.bonus_clicks, today.approved)}`,
  `└ Клик → Оплата школы:  ${calcRate(today.payments, today.bonus_clicks)}`,
  '',
  `📆 <b>Среднее за 7 дней:</b>`,
  `├ Стартов:              ${Math.round(week.starts || 0)}`,
  `├ Контактов:            ${Math.round(week.contacts || 0)}`,
  `├ Заявок:               ${Math.round(week.submissions || 0)}`,
  `├ Одобрено:             ${Math.round(week.approved || 0)}`,
  `├ Кликов:               ${Math.round(week.bonus_clicks || 0)}`,
  `└ Оплат:                ${Math.round(week.payments || 0)}`,
  '',
  '—',
  `🤖 Отчёт сгенерирован: ${new Date().toLocaleString('ru')}`
].join('\n');

// Bonus effectiveness
const bonusResult = await $('Supabase Call').execute({
  table: 'view_bonus_effectiveness',
  method: 'GET',
  filter: 'select=*'
});

const bonuses = bonusResult.first().json.rows || [];
if (bonuses.length > 0) {
  let bonusText = '\n\n🎁 <b>Популярность бонусов:</b>\n';
  for (const b of bonuses) {
    bonusText += `├ ${b.bonus_name || b.bonus_key}: кликов ${b.clicks || 0}, покупок ${b.purchases || 0}\n`;
  }
  // n8n will send this as a second message or appended

  return [{
    json: {
      chatId: config.MANAGERS_GROUP_CHAT_ID,
      text: reportText + bonusText,
      parse_mode: 'HTML'
    }
  }];
}

return [{
  json: {
    chatId: config.MANAGERS_GROUP_CHAT_ID,
    text: reportText,
    parse_mode: 'HTML'
  }
}];
