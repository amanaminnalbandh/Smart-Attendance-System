"""Offline backup. Stop the attendance server before running this command."""
from pathlib import Path
from datetime import datetime
import os
import zipfile

if __name__ == '__main__':
    answer = input('Server stopped? Type STOPPED to confirm: ')
    if answer != 'STOPPED':
        raise SystemExit('Stop the server first, then retry.')
    base = Path(__file__).resolve().parent
    data = Path(os.environ.get('SMART_ATTENDANCE_DATA_DIR', str(base / 'data'))).resolve()
    if not data.is_dir():
        raise SystemExit('No data directory found.')
    target = base / 'backups'
    target.mkdir(exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    destination = target / ('attendance-' + stamp + '.zip')
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
        for item in sorted(data.rglob('*')):
            if item.is_file():
                archive.write(item, 'data/' + item.relative_to(data).as_posix())
    print('Backup saved: ' + str(destination))
    print('This includes private face data and credentials. Keep it private.')
