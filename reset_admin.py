"""Local admin recovery. Stop server and run only as trusted laptop owner."""
import getpass
import json
import os
import secrets
from pathlib import Path
from werkzeug.security import generate_password_hash

if __name__ == '__main__':
    base = Path(__file__).resolve().parent
    data = Path(os.environ.get('SMART_ATTENDANCE_DATA_DIR', str(base / 'data'))).resolve()
    config_path = data / 'config.json'
    if not config_path.is_file():
        raise SystemExit('Local config absent. Use setup_project.py or rotate cloud environment credentials.')
    if input('Server stopped and you own this laptop? Type RESET: ') != 'RESET':
        raise SystemExit('No changes made.')
    config = json.loads(config_path.read_text('utf-8'))
    password = getpass.getpass('New admin password (12+ characters): ')
    repeat = getpass.getpass('Repeat password: ')
    if password != repeat or len(password) < 12:
        raise SystemExit('Passwords must match with at least 12 characters.')
    config['password_hash'] = generate_password_hash(password, method='scrypt')
    config['secret_key'] = secrets.token_hex(32)
    temporary = data / 'config-reset.tmp'
    with temporary.open('x', encoding='utf-8') as stream:
        json.dump(config, stream, indent=2)
    os.replace(temporary, config_path)
    try:
        os.chmod(config_path, 0o600)
    except OSError:
        pass
    print('Password changed, old sessions invalidated. Username: ' + config['admin_username'])
    print('Students, attendance and face data were preserved. Restart the server.')
