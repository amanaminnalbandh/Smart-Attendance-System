# Update an existing installation to English

This update changes interface and documentation language. It uses the same APIs and database schema. Keep your existing username, password, students, attendance, face samples and trained model.

## 1. Stop the application

Press **Ctrl+C** in the PowerShell window running `app.py`. Close the app's browser tabs while replacing files.

## 2. Back up your existing data

Open PowerShell in your **existing project folder**, which contains your current `app.py`. Use its existing environment and backup helper:

```powershell
.\.venv\Scripts\python.exe backup_project.py
```

Type `STOPPED` when asked. Keep the resulting ZIP from `backups/` in a private location: it contains login configuration, attendance and face data.

If you set `SMART_ATTENDANCE_DATA_DIR`, the helper backs up that configured directory. Keep this setting unchanged.

## 3. Extract the English package separately

Extract the new ZIP to a different temporary folder and open its `smart-attendance` folder. Do not extract the complete new package over your existing installation.

The source package has no personal data. Your existing installation remains the location of your records and credentials.

## 4. Replace the interface folders

Copy these folders from the English package into your **existing application root**:

- `templates/`
- `static/`

When Windows asks about same-named files, choose to replace those files. These folders contain the interface code and styling.

Keep the existing `data/`, `.venv/` and `backups/`. Preserve the configuration file inside your data directory, database, face samples and trained model. If data is stored elsewhere, preserve that directory and its environment settings too. Do not replace or delete personal files.

You may also copy the English `README.md`, `VERIFICATION.md` and this `UPGRADE_TO_ENGLISH.md` into your existing project folder.

You do **not** need to rerun `setup_project.py`, reset your password, reinstall dependencies, delete the model or migrate the database for this update.

## 5. Restart and refresh

From your existing project folder, run:

```powershell
.\.venv\Scripts\python.exe app.py
```

Open [http://localhost:8000](http://localhost:8000). Press **Ctrl+F5** to reload without the old cached assets, then log in with your existing username and password.

## 6. Check the updated installation

Confirm that the dashboard, student form, face enrollment, QR scanner, QR card and status messages are in English. Check that existing students and attendance records are still present.

Use a test student to check QR scanning and CSV export. A language update does not require retraining a model that was already ready. Retrain only when you later change face samples or student status.

If old text remains, stop and restart the correct existing app, then press **Ctrl+F5** again. Ensure the folders were copied beside the `app.py` you run, rather than inside an extra nested folder.

## If you need to revert

Stop the app and restore your previous `templates/` and `static/` folders, if retained. If personal data has separately been damaged, restore the complete matching data backup while the server is stopped, then restart and verify the register. Keep all copies private.
