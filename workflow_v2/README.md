# CH-SPA Bot: Workflow V2 Structure

## How to build

1. Import `workflow_v2_template.json` into n8n
2. Fill real values in App Config
3. Run `supabase_schema.sql` in Supabase SQL Editor
4. Test each branch

## Node list (~38 nodes, down from 93)

### TRIGGERS (3)
| # | Name | Type | Purpose |
|---|------|------|---------|
| T1 | Telegram Trigger | telegramTrigger | All user events |
| T2 | Auto-Approve Cron | scheduleTrigger | Every 5 min, auto-approves pending submissions |
| T3 | Followup Cron | scheduleTrigger | Every 6 hours, sends reminders |
| T4 | Daily Report Cron | scheduleTrigger | Daily 09:00 MSK, conversion report |
| T5 | Bonus Redirect | webhook | GET /r/:userId/:bonusKey |
| T6 | Payment Webhook | webhook | POST from YooKassa |

### CORE LOGIC (4)
| # | Name | Type | Purpose |
|---|------|------|---------|
| C1 | App Config | code | All settings, keys, URLs |
| C2 | Supabase Call | code | Unified DB access (fetch inside) |
| C3 | Upsert User | code | Load/create user, build CRM |
| C4 | Router | switch | 26 outputs, routes to correct branch |

### PURCHASE FUNNEL (branches 0-9)
| Branch | Node Name | Type | Does |
|--------|-----------|------|------|
| 0 | Set Start State → Start Welcome | code → telegram | /start handler |
| 1 | Check Subscription → Ask Subscription | code → telegram | Verify channel sub |
| 2 | Mark Contact State → Ask Contact | code → telegram | Request phone |
| 3 | Save Contact → Ask Package | code → telegram | Save phone, show packages |
| 4-6 | Save Package → Ask Photo | code → telegram | Unified pack selector |
| 7 | Save Photo → Create Submission | code → telegram | Photo + anti-duplicate |
| 8-9 | Manual Override (admin only) | code → telegram | Rare manual approve/reject |

### REVIEW FUNNEL (branches 10-15)
| Branch | Node Name | Type |
|--------|-----------|------|
| 10 | Start Review → Ask Marketplace | code → telegram |
| 11 | Save Marketplace → Ask Screenshot | code → telegram |
| 12 | Save Screenshot → Ask Product Photo | code → telegram |
| 13 | Save Product Photo → Send to Review | code → telegram |
| 14-15 | Review Approve/Reject | code → telegram |

### SYSTEM COMMANDS (branches 16-22)
| Branch | Node Name | Type |
|--------|-----------|------|
| 16 | Build Status → Send Status | code → telegram |
| 17 | Build Back → Send Back | code → telegram |
| 18 | Build Continue → Send Continue | code → telegram |
| 19 | Reset User → Send Reset | code → telegram |
| 20 | Help Message | code → telegram |
| 21 | Export CSV | code → telegram |
| 22 | Admin Commands (stats/broadcast/user) | code → telegram |

### UPSELL (branches 23-24)
| Branch | Node Name | Type |
|--------|-----------|------|
| 23 | Upsell Yes → Create Payment | code → telegram |
| 24 | Upsell No | code → telegram |

### PHONE AS TEXT (branch 25)
| Branch | Node Name | Type |
|--------|-----------|------|
| 25 | Contact Required Message | code → telegram |

### AUTO-PROCESSES
| # | Name | Type | Purpose |
|---|------|------|---------|
| A1 | Auto-Approve | code | Cron → approve pending > 1h |
| A2 | Unified Followup | code | Cron → remind stuck users |
| A3 | Daily Report | code | Cron → conversion report |
| A4 | Bonus Redirect | code | Webhook → log click → 302 |
| A5 | Parse Payment Webhook | code | Webhook → parse YooKassa event |
| A6 | Payment Router → Update DB | switch → code | Route success/fail → update |

## Connection flow

```
[T1 Telegram Trigger]
    │
    ▼
[C1 App Config]
    │
    ▼
[C3 Upsert User]  ←── reads/writes Supabase via C2
    │
    ▼
[C4 Router]  26 outputs
    │
    ├──0──→  Start Welcome
    ├──1──→  Check Subscription
    ├──2──→  Ask Contact
    ├──3──→  Save Contact → Ask Package
    ├──4-6─→ Save Package → Ask Photo
    ├──7──→  Save Photo → Create Submission
    ├──8-9─→ Admin Manual Approve/Reject
    ├──10──→ Start Review
    ├──11──→ Save Marketplace → Ask Screenshot
    ├──12──→ Save Screenshot → Ask Product Photo
    ├──13──→ Save Product Photo → Notify Managers
    ├──14-15→ Review Approve/Reject
    ├──16──→ Status
    ├──17──→ Back
    ├──18──→ Continue
    ├──19──→ Reset
    ├──20──→ Help
    ├──21──→ Export CSV
    ├──22──→ Admin (stats/broadcast/user)
    ├──23──→ Upsell Yes → [Payment flow]
    ├──24──→ Upsell No
    └──25──→ Contact Required

[T2 Auto-Approve Cron] → [A1 Auto-Approve Code] → [C2 Supabase Call] → Telegram
[T3 Followup Cron]     → [A2 Followup Code]     → [C2 Supabase Call] → Telegram
[T4 Daily Report Cron] → [A3 Report Code]        → [C2 Supabase Call] → Telegram
[T5 Bonus Redirect]    → [A4 Redirect Code]      → [C2 Supabase Call] → 302
[T6 Payment Webhook]   → [A5 Parse Code] → [A6 Router] → [C2] → Telegram
```

## Key differences from V1

| Aspect | V1 (93 nodes) | V2 (~38 nodes) |
|--------|---------------|-----------------|
| Data storage | staticData (memory) | Supabase (persistent) |
| Supabase HTTP calls | 14 separate nodes | 1 unified Code node |
| Build+Send pairs | 11 pairs, 22 nodes | Merged into single nodes |
| Package selection | 3 separate nodes | 1 unified with DB lookup |
| Followup | 9 nodes (cron+code+router+6tg) | 2 nodes (cron+code) |
| Approve flow | Manual by admin | Auto after 1h timer |
| Bonus tracking | Missing | Webhook redirect + events |
| Daily report | Missing | Cron + view_conversion_summary |
| Idempotency | Missing | Unique constraints + checks |
| Anti-duplicate | None | DB constraint + code check |
