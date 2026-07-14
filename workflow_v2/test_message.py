import paramiko, sys, json
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('5.42.117.117', username='root', password='h,6K7p+q9XsbC5', timeout=10)

# Check getUpdates
stdin, stdout, stderr = ssh.exec_command(
    'curl -s --proxy http://127.0.0.1:8888 --connect-timeout 10 '
    '"https://api.telegram.org/bot8589709724:AAF8R-tki276jyAw69b1EhAEm2hp-5E2j_I/getUpdates"'
)
resp = stdout.read().decode().strip()
data = json.loads(resp)
print(f'getUpdates ok: {data.get("ok")}, result count: {len(data.get("result", []))}')
if data.get('result'):
    for u in data['result'][:3]:
        print(json.dumps(u, indent=2, ensure_ascii=False)[:500])

# Try send message
import subprocess
result = subprocess.run([
    'sshpass', '-p', 'Tel237441', 'ssh', '-o', 'StrictHostKeyChecking=no', 'root@144.31.171.32',
    'curl -s --connect-timeout 10 -X POST "https://api.telegram.org/bot8589709724:AAF8R-tki276jyAw69b1EhAEm2hp-5E2j_I/sendMessage" -H "Content-Type: application/json" -d \'{"chat_id":7260765133,"text":"/start"}\''
], capture_output=True, text=True, timeout=15)
print(f'Send message: {result.stdout.strip()}')

ssh.close()
