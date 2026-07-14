-- ============================================
-- CH-SPA Bot: Supabase Schema v2
-- Source of truth for all bot data
-- ============================================

-- 1. USERS — основной профиль пользователя
-- ============================================
CREATE TABLE IF NOT EXISTS users (
  id              BIGSERIAL PRIMARY KEY,
  telegram_id     BIGINT NOT NULL UNIQUE,
  username        TEXT,
  phone           TEXT,
  first_name      TEXT,
  last_name       TEXT,

  -- Funnel state machine
  user_state      TEXT NOT NULL DEFAULT 'new'
    CHECK (user_state IN (
      'new',
      'awaiting_subscription',
      'awaiting_contact',
      'awaiting_package',
      'awaiting_photo',
      'pending_approval',
      'approved',
      'awaiting_review_marketplace',
      'awaiting_review_screenshot',
      'awaiting_review_product_photo',
      'review_pending',
      'review_approved',
      'awaiting_upsell',
      'completed',
      'blocked'
    )),

  -- Selected package (after choice)
  selected_package TEXT
    CHECK (selected_package IN ('standard', 'premium', 'vip')),

  -- Bonus access
  bonus_access     TEXT NOT NULL DEFAULT 'locked'
    CHECK (bonus_access IN ('locked', 'unlocked')),

  -- Purchase status
  purchase_status  TEXT DEFAULT NULL
    CHECK (purchase_status IN ('pending', 'approved', 'rejected')),

  -- Timers
  last_seen        TIMESTAMPTZ DEFAULT now(),
  last_followup_at TIMESTAMPTZ,
  created_at       TIMESTAMPTZ DEFAULT now(),

  -- Referral (future)
  ref_code         TEXT UNIQUE,
  referred_by      BIGINT REFERENCES users(telegram_id)
);

CREATE INDEX idx_users_telegram ON users(telegram_id);
CREATE INDEX idx_users_state ON users(user_state);
CREATE INDEX idx_users_purchase_status ON users(purchase_status);


-- 2. SUBMISSIONS — заявки на покупку (фото чека)
-- ============================================
CREATE TABLE IF NOT EXISTS submissions (
  id              BIGSERIAL PRIMARY KEY,
  user_id         BIGINT NOT NULL REFERENCES users(telegram_id),
  package         TEXT NOT NULL
    CHECK (package IN ('standard', 'premium', 'vip')),
  photo_file_id   TEXT NOT NULL,
  photo_tg_url    TEXT,

  -- Status: pending → approved (auto after 1h) or rejected
  purchase_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (purchase_status IN ('pending', 'approved', 'rejected')),

  -- Auto-approve timer
  timer_started_at TIMESTAMPTZ DEFAULT now(),
  approved_at      TIMESTAMPTZ,

  -- Who processed (NULL = auto, admin_id = manual override)
  decided_by       BIGINT,
  decided_at       TIMESTAMPTZ,
  reject_reason    TEXT,

  created_at       TIMESTAMPTZ DEFAULT now()
);

-- Anti-duplicate: one user cannot have multiple pending purchase submissions
CREATE UNIQUE INDEX idx_submissions_one_pending
  ON submissions(user_id, purchase_status)
  WHERE purchase_status = 'pending';

CREATE INDEX idx_submissions_user ON submissions(user_id);
CREATE INDEX idx_submissions_status ON submissions(purchase_status);


-- 3. REVIEW_SUBMISSIONS — заявки на отзывы
-- ============================================
CREATE TABLE IF NOT EXISTS review_submissions (
  id                        BIGSERIAL PRIMARY KEY,
  user_id                   BIGINT NOT NULL REFERENCES users(telegram_id),
  marketplace               TEXT NOT NULL,
  review_screenshot_file_id TEXT NOT NULL,
  product_photo_file_id     TEXT NOT NULL,
  status                    TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'approved', 'rejected')),
  decided_by                BIGINT,
  decided_at                TIMESTAMPTZ,
  created_at                TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_review_user ON review_submissions(user_id);
CREATE INDEX idx_review_status ON review_submissions(status);


-- 4. BONUSES — справочник бонусов (lookup table)
-- ============================================
CREATE TABLE IF NOT EXISTS bonuses (
  id          BIGSERIAL PRIMARY KEY,
  package     TEXT NOT NULL
    CHECK (package IN ('standard', 'premium', 'vip')),
  bonus_key   TEXT NOT NULL,        -- короткий ключ: 'bonus_1', 'bonus_2', 'bonus_3'
  bonus_name  TEXT NOT NULL,        -- название бонуса: "Вводный урок школы X"
  school_name TEXT,                 -- название онлайн-школы
  real_url    TEXT NOT NULL,        -- реальная ссылка
  description TEXT,                 -- описание
  is_active   BOOLEAN DEFAULT true,
  created_at  TIMESTAMPTZ DEFAULT now(),

  UNIQUE(package, bonus_key)
);


-- 5. EVENTS — журнал всех событий воронки
-- ============================================
CREATE TABLE IF NOT EXISTS events (
  id          BIGSERIAL PRIMARY KEY,
  user_id     BIGINT NOT NULL,
  event_name  TEXT NOT NULL,
  -- event_name values:
  --   'start', 'subscription_confirmed', 'contact_saved',
  --   'package_selected', 'photo_uploaded', 'submission_created',
  --   'submission_approved', 'submission_rejected',
  --   'bonus_clicked', 'bonus_redirected',
  --   'review_started', 'review_marketplace_selected',
  --   'review_screenshot_uploaded', 'review_product_photo_uploaded',
  --   'review_approved', 'review_rejected',
  --   'upsell_offered', 'upsell_accepted', 'upsell_declined',
  --   'payment_created', 'payment_succeeded', 'payment_failed',
  --   'followup_sent', 'reset', 'blocked'

  payload     JSONB DEFAULT '{}',   -- гибкие данные: package, bonus_key, marketplace, amount...
  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_events_user ON events(user_id);
CREATE INDEX idx_events_name ON events(event_name);
CREATE INDEX idx_events_created ON events(created_at);
CREATE INDEX idx_events_payload ON events USING GIN(payload);


-- 6. PAYMENTS — платежи через YooKassa
-- ============================================
CREATE TABLE IF NOT EXISTS payments (
  id                BIGSERIAL PRIMARY KEY,
  user_id           BIGINT NOT NULL REFERENCES users(telegram_id),
  provider          TEXT NOT NULL DEFAULT 'yookassa',
  provider_payment_id TEXT,              -- ID платежа от YooKassa
  amount            NUMERIC(10,2) NOT NULL,
  currency          TEXT NOT NULL DEFAULT 'RUB',
  status            TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'succeeded', 'canceled', 'failed')),
  idempotency_key   TEXT NOT NULL UNIQUE,
  payload           JSONB DEFAULT '{}',
  created_at        TIMESTAMPTZ DEFAULT now(),
  updated_at        TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_payments_user ON payments(user_id);
CREATE INDEX idx_payments_provider ON payments(provider_payment_id);
CREATE INDEX idx_payments_status ON payments(status);


-- 7. BROADCASTS — история рассылок (для будущего)
-- ============================================
CREATE TABLE IF NOT EXISTS broadcasts (
  id            BIGSERIAL PRIMARY KEY,
  sent_by       BIGINT NOT NULL,
  message_text  TEXT NOT NULL,
  segment_filter JSONB DEFAULT '{}',
  recipient_count INTEGER DEFAULT 0,
  delivered_count INTEGER DEFAULT 0,
  created_at    TIMESTAMPTZ DEFAULT now()
);


-- ============================================
-- VIEW: Conversion summary
-- ============================================
CREATE OR REPLACE VIEW view_conversion_summary AS
WITH
  period AS (
    SELECT
      date_trunc('day', now())                 AS today_start,
      date_trunc('day', now()) + interval '1d' AS today_end,
      date_trunc('day', now()) - interval '7d' AS week_start
  ),
  today_events AS (
    SELECT e.event_name, e.payload, e.user_id
    FROM events e, period p
    WHERE e.created_at >= p.today_start AND e.created_at < p.today_end
  ),
  week_events AS (
    SELECT e.event_name, e.payload, e.user_id
    FROM events e, period p
    WHERE e.created_at >= p.week_start AND e.created_at < p.today_end
  )
SELECT
  'today' AS period,
  (SELECT count(*) FROM today_events WHERE event_name = 'start')                  AS starts,
  (SELECT count(*) FROM today_events WHERE event_name = 'contact_saved')          AS contacts,
  (SELECT count(*) FROM today_events WHERE event_name = 'package_selected')       AS packages,
  (SELECT count(*) FROM today_events WHERE event_name = 'submission_created')     AS submissions,
  (SELECT count(*) FROM today_events WHERE event_name = 'submission_approved')    AS approved,
  (SELECT count(*) FROM today_events WHERE event_name = 'bonus_clicked')          AS bonus_clicks,
  (SELECT count(*) FROM today_events WHERE event_name = 'review_approved')        AS reviews,
  (SELECT count(*) FROM today_events WHERE event_name = 'payment_succeeded')      AS payments,
  (SELECT count(DISTINCT user_id) FROM today_events)                              AS active_users
UNION ALL
SELECT
  'week' AS period,
  (SELECT count(*) FROM week_events WHERE event_name = 'start') / 7.0,
  (SELECT count(*) FROM week_events WHERE event_name = 'contact_saved') / 7.0,
  (SELECT count(*) FROM week_events WHERE event_name = 'package_selected') / 7.0,
  (SELECT count(*) FROM week_events WHERE event_name = 'submission_created') / 7.0,
  (SELECT count(*) FROM week_events WHERE event_name = 'submission_approved') / 7.0,
  (SELECT count(*) FROM week_events WHERE event_name = 'bonus_clicked') / 7.0,
  (SELECT count(*) FROM week_events WHERE event_name = 'review_approved') / 7.0,
  (SELECT count(*) FROM week_events WHERE event_name = 'payment_succeeded') / 7.0,
  (SELECT count(DISTINCT user_id) FROM week_events) / 7.0;


-- ============================================
-- VIEW: Bonus effectiveness (для аналитики)
-- ============================================
CREATE OR REPLACE VIEW view_bonus_effectiveness AS
SELECT
  b.package,
  b.bonus_key,
  b.bonus_name,
  b.school_name,
  count(DISTINCT e.user_id) FILTER (WHERE e.event_name = 'bonus_clicked') AS clicks,
  count(DISTINCT e.user_id) FILTER (WHERE e.event_name = 'payment_succeeded') AS purchases
FROM bonuses b
LEFT JOIN events e ON e.payload->>'bonus_key' = b.bonus_key
WHERE b.is_active = true
GROUP BY b.id, b.package, b.bonus_key, b.bonus_name, b.school_name
ORDER BY b.package, b.bonus_key;


-- ============================================
-- SEED: Default bonuses (placeholder URLs)
-- ============================================
INSERT INTO bonuses (package, bonus_key, bonus_name, school_name, real_url, description) VALUES
  ('standard', 'bonus_1', 'Вводный урок',    '', 'https://example.com/placeholder', 'Вводный урок онлайн-школы'),
  ('standard', 'bonus_2', 'Мини-курс',       '', 'https://example.com/placeholder', 'Мини-курс по теме'),
  ('standard', 'bonus_3', 'Чек-лист',        '', 'https://example.com/placeholder', 'Полезный чек-лист'),
  ('premium',  'bonus_1', 'Вводный урок',    '', 'https://example.com/placeholder', 'Вводный урок онлайн-школы'),
  ('premium',  'bonus_2', 'Мини-курс',       '', 'https://example.com/placeholder', 'Мини-курс по теме'),
  ('premium',  'bonus_3', 'Мастер-класс',    '', 'https://example.com/placeholder', 'Мастер-класс с экспертом'),
  ('vip',      'bonus_1', 'Вводный урок',    '', 'https://example.com/placeholder', 'Вводный урок онлайн-школы'),
  ('vip',      'bonus_2', 'Мини-курс',       '', 'https://example.com/placeholder', 'Мини-курс по теме'),
  ('vip',      'bonus_3', 'Полный курс',     '', 'https://example.com/placeholder', 'Полный доступ к курсу')
ON CONFLICT (package, bonus_key) DO NOTHING;
