"""Добавить console.log во все ключевые ноды для полной диагностики"""
import requests, sys, json
sys.stdout.reconfigure(encoding='utf-8')
BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
s.post(f'{BASE}/rest/login', json={'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com', 'password': '1234Ko4321'}, timeout=10)
V2_ID = 'oV8dWIoAUHRkLaSb'

s.post(f'{BASE}/rest/workflows/{V2_ID}/deactivate', timeout=30)
r = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf = r.json().get('data', r.json())
nodes = wf.get('nodes', [])

# 1. Добавим лог в начало Upsert User
for node in nodes:
    if node.get('name') == 'Upsert User':
        code = node['parameters']['jsCode']

        # Добавим лог и try/catch вокруг всего после polyfill
        old_start = 'const input = $input.first().json;'
        new_start = '''const input = $input.first().json;
console.log('UPSERT_USER: input keys=' + JSON.stringify(Object.keys(input)));
console.log('UPSERT_USER: has message=' + !!(input.message) + ' has callback_query=' + !!(input.callback_query));
console.log('UPSERT_USER: telegram_id=' + ((input.message||{}).from||(input.callback_query||{}).from||{}).id);'''

        if old_start in code:
            code = code.replace(old_start, new_start)
            node['parameters']['jsCode'] = code
            print('Added logging to Upsert User')
        break

# 2. Добавим лог в начало Start Welcome
for node in nodes:
    if node.get('name') == 'Start Welcome':
        code = node['parameters']['jsCode']

        old_return = 'return [{ json:'
        if old_return in code:
            new_return = '''console.log('START_WELCOME: executing. input keys=' + JSON.stringify(Object.keys($input.first().json)));
console.log('START_WELCOME: crm=' + JSON.stringify($input.first().json.crm));
console.log('START_WELCOME: telegram message present=' + !!($input.first().json.message || $input.first().json.callback_query));
try {
''' + code.split(old_return)[0].split('const input = $input.first().json;')[0] + '''
const input = $input.first().json;
console.log('START_WELCOME: processing...');
''' + code.split('const input = $input.first().json;')[1].split(old_return)[0] + old_return

            # Это сложно, давай проще
            # Просто добавим лог перед return
            pass

        if old_return in code and 'console.log' not in code.split(old_return)[0][-100:]:
            code = code.replace(old_return,
                'console.log("START_WELCOME: sending reply. replyText=" + text.substring(0,50) + " chatId=" + ((input.message || input.callback_query.message).chat.id));\n' + old_return)
            node['parameters']['jsCode'] = code
            print('Added logging to Start Welcome')
        break

# 3. Добавим лог в Process Updates
for node in nodes:
    if node.get('name') == 'Process Updates':
        code = node['parameters']['jsCode']
        if 'const data' in code and 'console.log' not in code[:200]:
            code = code.replace(
                'const data = $input.first().json;',
                'const data = $input.first().json;\nconsole.log("PROCESS_UPDATES: ok=" + data.ok + " results=" + (data.result ? data.result.length : 0) + " updates");'
            )
            node['parameters']['jsCode'] = code
            print('Added logging to Process Updates')
        break

# Upload
r2 = s.patch(f'{BASE}/rest/workflows/{V2_ID}', json={'nodes': nodes})
print(f'Update: {r2.status_code}')
if not r2.ok:
    print('Error:', r2.text[:500])
    sys.exit(1)

# Activate
r3 = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf2 = r3.json().get('data', r3.json())
v = wf2.get('versionId')
r4 = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': v}, timeout=60)
print(f'Activate: {r4.status_code}')
if not r4.ok:
    print('Error:', r4.json().get('message', r4.text)[:500])
else:
    print('WORKFLOW ACTIVE')
    print()
    print('Теперь отправь /start боту.')
    print('Потом я проверю консоль-логи выполнений и увижу где ошибка.')

s.close()
