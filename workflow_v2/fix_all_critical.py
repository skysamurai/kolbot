"""
Комплексное исправление всех критических багов CH-SPA V2 workflow.
1. Добавляет связь Start Welcome → Send Start Welcome
2. Исправляет .replyKeyboard → $json.replyKeyboard в 5 узлах
3. Добавляет reply_markup в Send Approve Messages и Send Followup Messages
4. Исправляет паттерны роутинга в App Config
5. Увеличивает лимит поллинга до 10
"""
import requests, json, sys, re
sys.stdout.reconfigure(encoding='utf-8')

BASE = 'https://n8n.ch-spa.com.ru'
s = requests.Session()
print('🔑 Логин в n8n...')
r = s.post(f'{BASE}/rest/login', json={
    'emailOrLdapLoginId': 'shat.pomoshnik@gmail.com',
    'password': '1234Ko4321'
}, timeout=10)
if not r.ok:
    print(f'❌ Ошибка логина: {r.status_code}')
    sys.exit(1)
print('✅ Логин OK')

V2_ID = 'oV8dWIoAUHRkLaSb'

# Деактивируем workflow перед изменениями
print('\n⏸️ Деактивация workflow...')
r = s.post(f'{BASE}/rest/workflows/{V2_ID}/deactivate', timeout=30)
print(f'  Статус: {r.status_code}')

# Получаем текущий workflow
r = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf = r.json().get('data', r.json())
nodes = wf.get('nodes', [])
conns = wf.get('connections', {})

fixes_applied = []

# =============================================
# ИСПРАВЛЕНИЕ 1: Связь Start Welcome → Send Start Welcome
# =============================================
print('\n🔧 Исправление 1: Связь Start Welcome → Send Start Welcome')
conns['Start Welcome'] = {
    'main': [[{'node': 'Send Start Welcome', 'type': 'main', 'index': 0}]]
}
fixes_applied.append('1. Связь Start Welcome → Send Start Welcome')
print('  ✅ Добавлена')

# =============================================
# ИСПРАВЛЕНИЕ 2: .replyKeyboard → $json.replyKeyboard
# =============================================
print('\n🔧 Исправление 2: Выражения reply_markup')
broken_nodes = [
    'Send Start Welcome',
    'Send Check Sub',
    'Send Contact Request',
    'Send Package Choice',
    'Send Photo Received'
]
for node in nodes:
    name = node.get('name', '')
    if name in broken_nodes:
        params = node.get('parameters', {})
        af = params.get('additionalFields', {})
        old_rm = af.get('reply_markup', '')
        if '.replyKeyboard' in str(old_rm):
            af['reply_markup'] = '={{ $json.replyKeyboard }}'
            params['additionalFields'] = af
            fixes_applied.append(f'2. {name}: .replyKeyboard → \\$json.replyKeyboard')
            print(f'  ✅ {name}')

# =============================================
# ИСПРАВЛЕНИЕ 3: reply_markup в Send Approve Messages и Send Followup Messages
# =============================================
print('\n🔧 Исправление 3: reply_markup в Approve/Followup')
for node in nodes:
    name = node.get('name', '')
    if name in ['Send Approve Messages', 'Send Followup Messages']:
        params = node.get('parameters', {})
        af = params.get('additionalFields', {})
        af['reply_markup'] = '={{ $json.replyKeyboard }}'
        params['additionalFields'] = af
        fixes_applied.append(f'3. {name}: добавлен reply_markup')
        print(f'  ✅ {name}')

# =============================================
# ИСПРАВЛЕНИЕ 4: Паттерны роутинга в App Config
# =============================================
print('\n🔧 Исправление 4: Паттерны роутинга в App Config')
for node in nodes:
    if node.get('name') == 'App Config':
        old_code = node.get('parameters', {}).get('jsCode', '')

        # Исправляем условие для route 16: добавляем /status и правильные тексты
        old_route16 = "} else if (text === '📍 Мой статус' || text === '/status') {"
        new_route16 = "} else if (text === '📌 Мой статус' || text === '/status' || text === '📍 Мой статус') {"
        if old_route16 in old_code:
            old_code = old_code.replace(
                "} else if (text === '📌 Мой статус') {",
                "} else if (text === '📌 Мой статус' || text === '/status' || text === '📍 Мой статус') {"
            )

        # route 17: добавляем /back и старые тексты
        old_code = old_code.replace(
            "} else if (cbData === 'BACK_TO_MAIN' || text === '🔙 Назад') {",
            "} else if (cbData === 'BACK_TO_MAIN' || text === '🔙 Назад' || text === '⬅️ Назад' || text === '/back') {"
        )

        # route 18: добавляем /continue
        old_code = old_code.replace(
            "} else if (cbData === 'CONTINUE' || text === '▶️ Продолжить') {",
            "} else if (cbData === 'CONTINUE' || text === '▶️ Продолжить' || text === '/continue') {"
        )

        # route 19: добавляем /reset и старый текст
        old_code = old_code.replace(
            "} else if (cbData === 'RESET_STATE' || text === '🔄 Сбросить') {",
            "} else if (cbData === 'RESET_STATE' || text === '🔄 Сбросить' || text === '🔄 Начать заново' || text === '/reset') {"
        )

        # route 20: добавляем /help и старый текст
        old_code = old_code.replace(
            "} else if (cbData === 'HELP' || text === '❇️ Помощь') {",
            "} else if (cbData === 'HELP' || text === '❇️ Помощь' || text === '💬 Помощь' || text === '/help') {"
        )

        # route 21: добавляем /export_users текстовую команду
        old_code = old_code.replace(
            "} else if (cbData === 'ADMIN_EXPORT' && fromId === adminId) {",
            "} else if ((cbData === 'ADMIN_EXPORT' || text === '/export_users') && fromId === adminId) {"
        )

        # route 22: добавляем /broadcast, /stats, /user
        old_code = old_code.replace(
            "} else if (text.startsWith('/admin') && fromId === adminId) {",
            "} else if (fromId === adminId && (text.startsWith('/admin') || text.startsWith('/broadcast') || text === '/stats' || text.startsWith('/user'))) {"
        )

        node['parameters']['jsCode'] = old_code
        fixes_applied.append('4. Паттерны роутинга обновлены (добавлены /status, /back, /continue, /reset, /help, /export_users, /broadcast, /stats, /user)')
        print('  ✅ Паттерны роутинга обновлены')
        break

# =============================================
# ИСПРАВЛЕНИЕ 5: Лимит поллинга 1 → 10
# =============================================
print('\n🔧 Исправление 5: Лимит поллинга 1 → 10')
for node in nodes:
    if node.get('name') == 'Prepare URL':
        old_code = node.get('parameters', {}).get('jsCode', '')
        if 'limit=1' in old_code:
            new_code = old_code.replace('limit=1', 'limit=10')
            # Также меняем timeout=0 → timeout=30 для long polling
            new_code = new_code.replace('timeout=0', 'timeout=30')
            node['parameters']['jsCode'] = new_code
            fixes_applied.append('5. Лимит поллинга: 1→10, timeout: 0→30')
            print('  ✅ limit=1→10, timeout=0→30')
        break

# =============================================
# ЗАГРУЗКА ИЗМЕНЕНИЙ
# =============================================
print('\n📤 Загрузка изменений на сервер...')
r = s.patch(f'{BASE}/rest/workflows/{V2_ID}', json={
    'nodes': nodes,
    'connections': conns
}, timeout=30)

if r.ok:
    result = r.json().get('data', r.json())
    print(f'  ✅ Статус: {r.status_code}')
    print(f'  Всего узлов: {len(result.get("nodes", []))}')
else:
    print(f'  ❌ Ошибка: {r.status_code}')
    print(f'  {r.text[:500]}')
    sys.exit(1)

# =============================================
# АКТИВАЦИЯ
# =============================================
print('\n▶️ Активация workflow...')
r = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf2 = r.json().get('data', r.json())
version_id = wf2.get('versionId')
r = s.post(f'{BASE}/rest/workflows/{V2_ID}/activate', json={'versionId': version_id}, timeout=60)

if r.ok:
    print('  ✅ Workflow активирован!')
else:
    msg = r.json().get('message', r.text[:500])
    print(f'  ⚠️ Активация: {r.status_code} — {msg}')

# =============================================
# ПРОВЕРКА
# =============================================
print('\n📋 Проверка исправлений:')
r = s.get(f'{BASE}/rest/workflows/{V2_ID}')
wf3 = r.json().get('data', r.json())
nodes3 = wf3.get('nodes', [])
conns3 = wf3.get('connections', {})

# Проверка 1: связь Start Welcome
sw_conn = conns3.get('Start Welcome', {})
has_sw = any(
    t.get('node') == 'Send Start Welcome'
    for branch in sw_conn.get('main', [])
    for t in branch
)
print(f'  {"✅" if has_sw else "❌"} Связь Start Welcome → Send Start Welcome')

# Проверка 2: выражения reply_markup
for node in nodes3:
    name = node.get('name', '')
    if name in broken_nodes:
        rm = node.get('parameters', {}).get('additionalFields', {}).get('reply_markup', '')
        if '$json.replyKeyboard' in str(rm):
            print(f'  ✅ {name}: reply_markup = $json.replyKeyboard')
        else:
            print(f'  ❌ {name}: reply_markup = {rm}')

# Проверка 3: Approve/Followup
for node in nodes3:
    name = node.get('name', '')
    if name in ['Send Approve Messages', 'Send Followup Messages']:
        rm = node.get('parameters', {}).get('additionalFields', {}).get('reply_markup', '')
        if 'replyKeyboard' in str(rm):
            print(f'  ✅ {name}: reply_markup добавлен')
        else:
            print(f'  ❌ {name}: reply_markup отсутствует')

# Проверка 4: Паттерны роутинга
for node in nodes3:
    if node.get('name') == 'App Config':
        code = node.get('parameters', {}).get('jsCode', '')
        checks = ['/status', '/back', '/continue', '/reset', '/help', '/export_users', '/broadcast', '/stats', '/user']
        for c in checks:
            if c in code:
                print(f'  ✅ Команда {c} в роутере')
            else:
                print(f'  ❌ Команда {c} отсутствует в роутере')
        break

# Проверка 5: Лимит поллинга
for node in nodes3:
    if node.get('name') == 'Prepare URL':
        code = node.get('parameters', {}).get('jsCode', '')
        if 'limit=10' in code:
            print('  ✅ Лимит поллинга = 10')
        else:
            print(f'  ⚠️ Лимит поллинга не изменён')
        if 'timeout=30' in code:
            print('  ✅ Timeout = 30')
        else:
            print(f'  ⚠️ Timeout не изменён')
        break

print(f'\n🎯 Всего исправлений: {len(fixes_applied)}')
for f in fixes_applied:
    print(f'  • {f}')

print(f'\n🔗 Открыть workflow: {BASE}/workflow/{V2_ID}')
s.close()
