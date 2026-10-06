"""First-run setup. Run locally in a terminal, never through the web server."""
import getpass
import json
import os
import secrets
from pathlib import Path

from werkzeug.security import generate_password_hash

from app import init_db


def main():
    default_dir = Path(__file__).resolve().parent / "data"
    data_dir = Path(os.environ.get("SMART_ATTENDANCE_DATA_DIR", default_dir)).resolve()
    config_path = data_dir / "config.json"
    if config_path.exists():
        print(f"Already set up: {config_path}. Your existing password is unchanged.")
        return
    username = input("Teacher/admin username [admin]: ").strip() or "admin"
    if len(username) > 80:
        raise SystemExit("Username must be 80 characters or fewer.")
    while True:
        password = getpass.getpass("New admin password (at least 12 characters): ")
        repeat = getpass.getpass("Repeat password: ")
        if len(password) < 12:
            print("Please use at least 12 characters.")
        elif password != repeat:
            print("Passwords do not match. Try again.")
        else:
            break
    data_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "admin_username": username,
        "password_hash": generate_password_hash(password, method="scrypt"),
        "secret_key": secrets.token_hex(32),
        "face_threshold": 65.0,
    }
    # Exclusive creation avoids accidentally replacing an existing credential file.
    with config_path.open("x", encoding="utf-8") as handle:
        json.dump(config, handle, indent=2)
    try:
        os.chmod(config_path, 0o600)
    except OSError:
        pass
    init_db(data_dir)
    print("Setup complete. Keep the data folder private; it contains biometric data.")
    start_command = r".\.venv\Scripts\python.exe app.py" if os.name == "nt" else ".venv/bin/python app.py"
    print(f"Start: {start_command}   Then open http://localhost:8000")


if __name__ == "__main__":
    main()
