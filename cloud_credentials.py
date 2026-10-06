"""Generate environment credentials locally; never commit the printed values."""
import getpass
import secrets
from werkzeug.security import generate_password_hash

if __name__ == '__main__':
    password = getpass.getpass('Cloud admin password (12+ characters): ')
    repeated = getpass.getpass('Repeat password: ')
    if password != repeated or len(password) < 12:
        raise SystemExit('Passwords must match and contain at least 12 characters.')
    print('\nPaste these values only into your hosting environment settings:')
    print('SMART_ATTENDANCE_SECRET=' + secrets.token_hex(32))
    print('SMART_ATTENDANCE_ADMIN_HASH=' + generate_password_hash(password))
    print('SMART_ATTENDANCE_ADMIN_USER=admin')
    print('Keep these values private. Do not upload them to your repository.')
