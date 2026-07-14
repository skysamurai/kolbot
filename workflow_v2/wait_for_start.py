"""Deactivate workflow, wait for user to send /start, then test keyboard directly"""
import requests, sys, json, time
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)
V2_ID = 'oV8dWIoAUHRkLaSb'
BOT_TOKEN = '8589709724:AAF8R-tki276jyAw69b1EhAEm2hp-5E2j_I'

# Deactivate workflow
s.post(f'{BASE}/rest/workflows/{V2_ID}/deactivate', timeout=30)
print('Workflow DEACTIVATED.')

# Get current max update_id to use as baseline
r = requests.get(f'https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?limit=1', timeout=10)
data = r.json()
if data.get('result'):
    baseline = data['result'][-1]['update_id']
    print(f'Baseline update_id: {baseline}')
else:
    baseline = 0
    print('No baseline updates')

print()
print('*** SEND /start TO THE BOT NOW ***')
print('Waiting 15 seconds for you to send /start...')

# Wait for the user
time.sleep(5)
print('10 seconds remaining...')
time.sleep(5)
print('5 seconds remaining...')
time.sleep(5)

# Check for new updates
r = requests.get(f'https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset={baseline+1}&limit=5', timeout=10)
data = r.json()
updates = data.get('result', [])

if updates:
    print(f'\nFound {len(updates)} new update(s)!')
    for upd in updates:
        msg = upd.get('message') or upd.get('callback_query', {}).get('message', {})
        chat_id = msg.get('chat', {}).get('id')
        text = msg.get('text', '')[:80]
        print(f'  chat_id={chat_id} text={text}')

        if chat_id:
            # Send test message with keyboard
            print(f'\nSending test message to chat_id={chat_id}...')
            test_msg = {
                'chat_id': chat_id,
                'text': 'ТЕСТ: проверка клавиатуры (напрямую через API)',
                'reply_markup': {
                    'inline_keyboard': [[
                        {'text': 'ТЕСТ КНОПКА', 'callback_data': 'TEST_DIRECT'}
                    ]]
                }
            }
            r2 = requests.post(
                f'https://api.telegram.org/bot{BOT_TOKEN}/sendMessage',
                json=test_msg,
                timeout=10
            )
            result = r2.json()
            print(f'Response: {json.dumps(result, ensure_ascii=False)}')

            if result.get('ok'):
                print('\n=== CHECK TELEGRAM NOW ===')
                print('If you see "ТЕСТ КНОПКА" button → n8n is the problem')
                print('If you see NO button → bot token or Telegram API issue')
            else:
                print(f'FAILED: {result.get("description")}')
else:
    print('\nNo new updates found. The /start might not have been received.')
    print('Please try sending /start again after reactivation.')

# Reactivate
r3 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf = r3.json().get('data', r3.json())
v = wf.get('versionId')
r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': v}, timeout=60)
print(f'\nWorkflow reactivated: {r4.status_code}')

s.close()
