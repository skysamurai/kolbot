"""Get the user's chat_id from execution data and send a direct Telegram test"""
import requests, sys, json, re
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)
V2_ID = 'oV8dWIoAUHRkLaSb'
BOT_TOKEN = '8589709724:AAF8R-tki276jyAw69b1EhAEm2hp-5E2j_I'

# First, temporarily deactivate to stop polling
s.post(f'{BASE}/rest/workflows/{V2_ID}/deactivate', timeout=30)
print('Deactivated workflow')

# Now call getUpdates from Python to find the chat_id
r = requests.get(f'https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?limit=10', timeout=10)
data = r.json()
print(f'getUpdates: ok={data.get("ok")}, results={len(data.get("result", []))}')

chat_id = None
for update in data.get('result', []):
    msg = update.get('message') or update.get('callback_query', {}).get('message', {})
    cid = msg.get('chat', {}).get('id')
    text = msg.get('text', '')[:80]
    username = msg.get('chat', {}).get('username', '?')
    print(f'  update_id={update["update_id"]} chat_id={cid} username={username} text={text}')
    if cid:
        chat_id = cid  # Use the last one

if chat_id:
    print(f'\nFound chat_id: {chat_id}')
    print('Sending test message with keyboard...')

    test_msg = {
        'chat_id': chat_id,
        'text': 'Тест клавиатуры напрямую через API',
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
        print('SUCCESS! Check Telegram for the test message.')
        print('If you see the button, the issue is with n8n.')
        print('If you do NOT see the button, the issue is with Telegram API or bot token.')
    else:
        print(f'FAILED: {result.get("description")}')
else:
    print('No chat_id found. Ask the user to send /start first.')

# Reactivate workflow
r3 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf = r3.json().get('data', r3.json())
v = wf.get('versionId')
r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': v}, timeout=60)
print(f'Reactivate: {r4.status_code}')

s.close()
