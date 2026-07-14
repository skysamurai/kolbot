// ============================================
// NODE: Supabase Call (UNIFIED)
// Type: Code
// ============================================
// Replaces 14 separate HTTP nodes.
// Every branch that needs Supabase routes through this.
//
// INPUT (from any branch):
//   table:  "users" | "submissions" | "review_submissions" | "events" | "payments" | "bonuses"
//   method: "GET" | "POST" | "PATCH" | "DELETE"
//   body:   { ... }  (for POST/PATCH)
//   filter: "telegram_id=eq.123&select=*"  (for GET/PATCH/DELETE)
//   upsert: true  (for POST with ON CONFLICT)
//   onConflict: "telegram_id"  (column for upsert)
//
// OUTPUT:
//   json.rows:    array of result rows
//   json.row:     first result row (convenience)
//   json.error:   error message if failed
//   json.ok:      boolean
// ============================================

const MAX_RETRIES = 3;
const RETRY_DELAY_MS = 1000;

const config = $('App Config').first().json.app_config;
const baseUrl = config.SUPABASE_REST_URL;
const apiKey  = config.SUPABASE_SERVICE_ROLE_KEY;

if (!baseUrl || !apiKey) {
  return [{ json: { ok: false, error: 'Supabase not configured', rows: [] } }];
}

const input = $input.first().json;

const table  = String(input.table || '');
const method = String(input.method || 'GET').toUpperCase();
const filter = String(input.filter || '');
const body   = input.body || null;
const upsert = Boolean(input.upsert);
const onConflict = input.onConflict || '';

// Build URL
let url = `${baseUrl}/${table}`;
if (filter) {
  url += `?${filter}`;
}

// Build headers
const headers = {
  'apikey': apiKey,
  'Authorization': `Bearer ${apiKey}`,
  'Content-Type': 'application/json',
  'Prefer': upsert ? `resolution=merge-duplicates` : 'return=representation'
};

if (upsert && onConflict) {
  headers['Prefer'] = `resolution=merge-duplicates`;
}

// Build fetch options
const fetchOptions = {
  method: method,
  headers: headers
};

if (['POST', 'PATCH', 'PUT'].includes(method) && body) {
  fetchOptions.body = JSON.stringify(body);
}

// Execute with retry
let lastError = null;
for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
  try {
    const response = await fetch(url, fetchOptions);
    const text = await response.text();

    if (response.ok) {
      let data;
      try { data = JSON.parse(text); } catch { data = text; }
      const rows = Array.isArray(data) ? data : [data];
      return [{
        json: {
          ok: true,
          rows: rows,
          row: rows[0] || null,
          count: rows.length,
          status: response.status
        }
      }];
    }

    // 4xx — client error, no retry
    if (response.status >= 400 && response.status < 500) {
      return [{
        json: {
          ok: false,
          error: `Supabase error ${response.status}: ${text}`,
          rows: [],
          status: response.status
        }
      }];
    }

    // 5xx — server error, retry
    lastError = `Supabase ${response.status}: ${text}`;

  } catch (err) {
    lastError = err.message;
  }

  // Exponential backoff before retry
  if (attempt < MAX_RETRIES) {
    await new Promise(r => setTimeout(r, RETRY_DELAY_MS * Math.pow(2, attempt)));
  }
}

// All retries failed
return [{
  json: {
    ok: false,
    error: `Supabase unreachable after ${MAX_RETRIES} retries: ${lastError}`,
    rows: []
  }
}];
