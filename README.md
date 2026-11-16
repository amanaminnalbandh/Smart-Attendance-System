# 🛡️ Smart Attendance System — Face Recognition & QR Code

A supervised educational attendance project built for Windows. This system utilizes a hybrid approach, combining real-time OpenCV face recognition and dynamic QR code scanning with a lightweight Python Flask backend. It features teacher-audited corrections, secure local data processing, and comprehensive CSV reporting.

---



---

## 🎯 Project Overview
This project eliminates proxy attendance by enforcing physical presence through supervised biometric and QR validations. It is designed to run locally on a Windows machine, ensuring face data remains on the device without relying on external APIs. A teacher or admin can review daily logs, manually correct marks, and export detailed audit reports.

## 🛠️ Technical Stack
* **Backend:** Python 3.12, Flask
* **Computer Vision:** OpenCV (LBPH Face Recognizer, Haar Cascades)
* **Database:** mongodb
* **Frontend:** HTML5, CSS3, JavaScript (Webcam integration)
* **Deployment:** Localhost (Windows PowerShell), optional Cloud (Render)

## ✨ Key Features
1. **Hybrid Verification:** Choose between Face Recognition (requires volunteer enrollment and model training) or secure QR Code scanning.
2. **Offline Biometrics:** Uses OpenCV's LBPH distance for local facial recognition without transmitting biometric data to third-party APIs.
3. **Admin Dashboard:** Secure login portal for teachers to manage students, review attendance, and manually void/correct marks.
4. **Data Integrity:** Generates exportable CSV reports for both daily attendance and administrative audit logs.
5. **Secure Local Environment:** Includes automated scripts for creating backups (`backup_project.py`) and resetting passwords (`reset_admin.py`).

---

## 🚀 Installation & Setup (Windows)

### Prerequisites
* Windows 10 or 11
* 64-bit **Python 3.12**
* A modern browser with camera support (Edge, Chrome)
* A working webcam

### 1. Environment Setup
Extract the project ZIP to a writable location (e.g., Documents). Open the folder containing `app.py` in File Explorer, type `powershell` in the address bar, and press Enter.

Verify Python and create a virtual environment:
```powershell
python --version
python -m venv .venv


2. Install Dependencies

.\.venv\Scripts\python.exe -m pip install -r requirements.txt

3. Admin Configuration
Run the setup script to create your private data/ folder and teacher login:
.\.venv\Scripts\python.exe setup_project.py

4. Run the Application
.\.venv\Scripts\python.exe app.py

Access the dashboard at http://localhost:8000 and log in.

Usage Guide
Registering Students & QR Attendance
Add a student via the dashboard with a unique code and name.

Download their generated QR PNG.

Open the QR scanner page and present the QR code to the webcam to log attendance.

Note: "Reissue QR" invalidates previous cards.

Face Enrollment & Training
Obtain explicit consent from volunteers before enabling face enrollment.

Open the student's face-samples page (requires camera access).

Capture at least 25 clear, well-lit samples per student.

Return to the dashboard and click Train Model.

Open the face scanner. A successful mark requires three consecutive matches within a 4-second window.

Auditing & Corrections
Review: Download the attendance CSV to review daily records (India Standard Time).

Correct: Use verified manual entry with a reason, or void an incorrect mark. All actions are logged in the audit CSV.

Deactivate: Deactivating a student invalidates their QR and recognition but preserves past data.


🛠️ Maintenance & Troubleshooting
Utilities
Backup Data: Stop the server and run .\.venv\Scripts\python.exe backup_project.py. This creates a secure ZIP in backups/.

Reset Password: Stop the server and run .\.venv\Scripts\python.exe reset_admin.py.

Optional Cloud Hosting (Render)
While designed for local execution, the app can be hosted using headless OpenCV.

Required Environment Variables:

Plaintext
HOST=0.0.0.0
PORT=<host_port>
SMART_ATTENDANCE_DATA_DIR=/var/data/attendance  # Requires Persistent Disk
SECURE_COOKIE=1
SMART_ATTENDANCE_ADMIN_USER=admin
SMART_ATTENDANCE_SECRET=<generated_secret>
SMART_ATTENDANCE_ADMIN_HASH=<generated_hash>
