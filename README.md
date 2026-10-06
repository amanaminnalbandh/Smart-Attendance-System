# Smart Attendance — Face + QR

A supervised educational attendance project for a Windows laptop. The interface, instructions and companion guide are in English. A teacher reviews the results and can make audited corrections.

## Updating an existing installation

Follow [UPGRADE_TO_ENGLISH.md](UPGRADE_TO_ENGLISH.md). Stop the app, back up your records, and replace only `templates/` and `static/` with the English folders. Keep `data/` and `.venv/`. You do not need to reinstall packages, repeat setup or migrate the database.

## What you need

- Windows 10 or 11 and 64-bit Python 3.12.
- Microsoft Edge, Google Chrome or another browser with camera support.
- A working webcam for face enrollment and camera scanning.
- Internet access for the initial installation. Local attendance processing does not use an external face-recognition API.
- Volunteers who explicitly agree to face enrollment. QR attendance works without face enrollment.

The source package includes the app and an official pretrained OpenCV face detector. It contains no personal credentials, student database, enrolled student faces or trained student identity model.

## 1. Extract and open the project folder

Extract the complete ZIP to a writable location, such as your Documents folder. Open the `smart-attendance` folder containing `app.py`, `requirements.txt` and `setup_project.py`.

In File Explorer, click the address bar, type `powershell` and press Enter. Run every project command from this folder. If the terminal shows `C:\Windows\System32`, return to the extracted project folder first.

Keep the complete folder together, including `assets/`, `templates/` and `static/`. Do not run the app directly inside the ZIP.

## 2. Check Python

Check an existing installation first:

```powershell
python --version
```

If it shows `Python 3.12.x`, use it to create the project environment. The `py` command is not required:

```powershell
python -m venv .venv
```

If Python is missing or another version is selected, install the official [Python Install Manager](https://www.python.org/downloads/), reopen PowerShell in the project folder, then run:

```powershell
pymanager install 3.12
py -3.12 --version
py -3.12 -m venv .venv
```

These are alternative ways to create the same `.venv` folder. The manager's `pymanager` command avoids confusion with an older `py` launcher. See the official [Python Windows instructions](https://docs.python.org/3/using/windows.html).

## 3. Install the libraries

Use the project's environment for every remaining command:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Wait for installation to finish successfully. Environment activation is optional because these commands use its Python directly.

## 4. Create your teacher/admin login

Run setup once:

```powershell
.\.venv\Scripts\python.exe setup_project.py
```

Enter a username, or press Enter to use `admin`. Choose your own password with at least 12 characters, then enter it again.

**Password typing is deliberately invisible:** the terminal shows neither letters nor dots. Type the password and press Enter normally. Keep your credentials private.

Setup creates the private `data/` folder. If the project is already set up, it keeps the existing login unchanged.

## 5. Start the app

```powershell
.\.venv\Scripts\python.exe app.py
```

Keep PowerShell open. Open [http://localhost:8000](http://localhost:8000) in your browser and log in with the credentials you chose.

This starts the app on your laptop. A public internet address requires separate hosting; local startup does not publish the project.

## 6. Register a student and test QR attendance

1. Enter a unique student code and name on the dashboard.
2. Select face-enrollment permission only when the student has agreed. Leave it unselected for QR-only attendance.
3. Add the student, open their QR card and download the PNG. Keep it private.
4. Open the QR scanner and show a printed card or a card on another screen to the webcam.
5. With only one laptop, upload the downloaded PNG on the QR scanner page. This tests decoding but does not prove physical presence.
6. Scan again to confirm that the student is already marked for that day.

A QR can be copied and used by someone else. Use it under teacher supervision. **Reissue QR** invalidates the previous card and creates a new one.

## 7. Enroll faces and train

1. Use at least two consenting volunteers where possible. Also test people who have not been enrolled.
2. Open a student's face-samples page and allow camera access.
3. Keep one clear face in the frame, with steady lighting and small natural changes in pose.
4. The page targets 25 accepted samples; training requires at least 20 valid samples per enrolled student.
5. Return to the dashboard and train the model.
6. Open the face scanner. A mark requires three consecutive matches for the same student and model, with no more than four seconds between matching requests.

Adding samples or activating/deactivating a student invalidates the model. Train again before using face attendance.

OpenCV LBPH distance is not an accuracy percentage. Test known and unknown volunteers in separate sessions and review incorrect matches. A one-person model is allowed for demonstration but can accept other people. Photos and videos can also fool it; liveness detection is not included.

## 8. Review and correct attendance

One student can have one attendance mark per India Standard Time date across face, QR and teacher-entered methods. This is a daily register; separate lectures, lateness and attendance percentages are not implemented.

- Download the attendance CSV to review saved records.
- Use verified manual entry when needed, with a reason.
- Void an incorrect mark with a reason. The original entry and reason remain in the audit log, and the student can then be marked correctly.
- Download the audit CSV to review corrections and administrative actions.

Deactivating a student prevents recognition and invalidates their QR. It retains their existing records and face samples; deactivation does not erase personal data.

## Repeat start and stop

Open PowerShell in the same project folder and run only:

```powershell
.\.venv\Scripts\python.exe app.py
```

Ordinary restarts do not require setup or library installation. Keep the server window open while using the browser. Press **Ctrl+C** there to stop it.

## Back up and restore records

Stop the server, then run:

```powershell
.\.venv\Scripts\python.exe backup_project.py
```

Type `STOPPED` when asked. The helper creates a ZIP in `backups/` containing the configured data directory, including private login configuration and face data. Keep it private and copy it to a secure location.

To restore, stop the server and back up the current data first. Restore a complete matching backup's `data/` contents to the app's data directory. Preserve the database, configuration, samples and model together. Restart, log in and verify the register. If you set `SMART_ATTENDANCE_DATA_DIR`, use that directory instead of the default `data/`.

## Recover a forgotten local password

On your trusted laptop, stop the server and run:

```powershell
.\.venv\Scripts\python.exe reset_admin.py
```

Type `RESET`, then enter and repeat a new password of at least 12 characters. Student records, attendance and faces are preserved; old login sessions are invalidated. For an environment-only cloud setup, generate new credentials with `cloud_credentials.py` and rotate the hosting environment settings instead.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| `python` is not recognized | Follow the Python installation steps, then reopen PowerShell. |
| `py` is missing but `python --version` shows 3.12 | Use `python -m venv .venv`; an existing Python installation does not require `py`. |
| A project file cannot be found | Open the folder containing `app.py`; avoid `System32` and running inside the ZIP. |
| No password characters appear | This is normal. Type the password, press Enter, then repeat it when asked. |
| A library cannot be imported | Install `requirements.txt` using `.\.venv\Scripts\python.exe` and start with the same Python. |
| The browser cannot connect | Check that the server is running and use `http://localhost:8000`. |
| The camera will not start | Allow browser and Windows camera access; close other apps using the webcam. Localhost and HTTPS support browser camera access. |
| No clear face is found | Improve lighting, face the camera, move closer and keep one face in the frame. |
| The model is not ready | Collect enough accepted samples and train after sample/status changes. |
| The detector is missing | Restore `assets/haarcascade_frontalface_default.xml` from the complete source ZIP. |
| Attendance is already marked | Review the existing daily entry; void it with a reason only if incorrect. |
| Old interface text remains | Restart the server and press **Ctrl+F5** in the browser. |

## Verification

Run the included backend tests with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

See [VERIFICATION.md](VERIFICATION.md) for recorded checks and limits. Automated checks do not establish real webcam accuracy, lighting performance or resistance to spoofing.

## Optional internet hosting

Cloud hosting is an untested option for this project. Use HTTPS, private administrator credentials and durable storage. Upload only source files; do not publish local `data/`, backups, credentials or `.venv/`.

For Render or an equivalent Python host, mount a persistent disk at `/var/data` and set `SMART_ATTENDANCE_DATA_DIR=/var/data/attendance`. Render's default filesystem is temporary, and persistent disks currently require a paid service. Check the current plan before deploying. Only files under the disk's mount path persist. See [Render persistent disks](https://render.com/docs/disks).

Use this project's commands rather than a generic tutorial's example application command:

```text
Build command: pip install -r requirements-cloud.txt
Start command: python app.py
```

Cloud requirements use headless OpenCV. Do not mix the full local OpenCV package and the headless package in one environment.

Set these hosting values:

```text
HOST=0.0.0.0
PORT=<the port supplied by your host>
SMART_ATTENDANCE_DATA_DIR=/var/data/attendance
SECURE_COOKIE=1
SMART_ATTENDANCE_ADMIN_USER=admin
SMART_ATTENDANCE_SECRET=<generated secret>
SMART_ATTENDANCE_ADMIN_HASH=<generated password hash>
```

Generate the last two values locally:

```powershell
.\.venv\Scripts\python.exe cloud_credentials.py
```

Keep the printed values private and paste them only into hosting environment settings. Set `TRUST_PROXY=1` only behind one trusted proxy supplying the expected forwarded headers; follow the host's proxy configuration.

Keep one application process/service instance for this SQLite and face-model design. Verify login, persistence across restarts, QR decoding and camera access on the HTTPS address before enrolling real students. In cloud mode, browser images go to your hosted app rather than staying on the laptop. The server processes them with OpenCV and does not need its own webcam.

See [Render's Flask deployment instructions](https://render.com/docs/deploy-flask) for service creation. This project has not been deployed or validated on Render.
